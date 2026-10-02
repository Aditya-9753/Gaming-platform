"""Wallet service — all credit-movement operations.

NON-NEGOTIABLE RULES:
1. Every credit movement acquires a SELECT … FOR UPDATE on the wallet row.
2. Every movement writes one WalletTransaction row with:
   balance_before / amount / balance_after / type / status / reference / idempotency_key.
3. All amounts are stored as integer paise.  No floats.
4. Same idempotency_key + same payload → return the original result (cached TX).
   Same idempotency_key + different payload → IdempotencyException.
5. Balances must never go negative.  locked_balance must never exceed balance.
6. Every method commits or rolls back; caller must NOT commit.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TransactionStatus, TransactionType
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    IdempotencyException,
    InsufficientBalanceException,
    NotFoundException,
)
from app.core.logging import get_logger
from app.models.audit_log import AuditLog
from app.models.wallet import Wallet, WalletTransaction
from app.repositories.wallet_repo import WalletRepository
from app.utils.idempotency import check_idempotency, store_idempotency_result
from app.utils.money import (
    format_credits,
    validate_positive_paise,
    validate_sufficient_balance,
    validate_transaction_limit,
)

logger = get_logger("wallet_service")


class WalletService:
    """Orchestrates all virtual-credit movements.

    All public methods run inside a single transaction and commit on success.
    On any exception the session must be rolled back by the caller (FastAPI's
    ``get_db`` dependency does this automatically on exceptions).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._db = session
        self._repo = WalletRepository(session)

    # ------------------------------------------------------------------
    # Internal: locked wallet helper
    # ------------------------------------------------------------------

    async def _get_locked_wallet(self, user_id: str) -> Wallet:
        """Acquire row-level lock on the wallet.  Raises NotFoundException."""
        wallet = await self._repo.get_wallet_for_update(user_id)
        if wallet is None:
            raise NotFoundException(f"Wallet not found for user {user_id}")
        if wallet.is_frozen:
            raise ForbiddenException("Wallet is frozen — contact support")
        return wallet

    async def _write_tx(
        self,
        wallet: Wallet,
        *,
        idem_key: str,
        tx_type: TransactionType,
        amount: int,
        balance_before: int,
        balance_after: int,
        status: TransactionStatus = TransactionStatus.COMPLETED,
        reference: Optional[str] = None,
        description: Optional[str] = None,
    ) -> WalletTransaction:
        """Create and flush an immutable ledger row."""
        tx = WalletTransaction(
            id=str(uuid.uuid4()),
            wallet_id=wallet.id,
            idempotency_key=idem_key,
            type=tx_type.value,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            status=status.value,
            reference=reference,
            description=description,
        )
        return await self._repo.add_transaction(tx)

    # ------------------------------------------------------------------
    # place_bet: available → locked
    # ------------------------------------------------------------------

    async def place_bet(
        self,
        user_id: str,
        amount_paise: int,
        idempotency_key: str,
        reference: Optional[str] = None,
        description: Optional[str] = None,
    ) -> WalletTransaction:
        """Deduct from available balance and add to locked balance.

        locked_balance represents money committed to an active wager.
        The caller (game service) holds onto the idempotency_key to settle later.
        """
        validate_transaction_limit(amount_paise, "bet amount")

        payload = {"user_id": user_id, "amount": amount_paise, "reference": reference}

        # Idempotency check — replay if already processed
        cached = await check_idempotency(idempotency_key, payload)
        if cached is not None:
            existing = await self._repo.get_transaction_by_idempotency_key(idempotency_key)
            if existing:
                return existing
            raise IdempotencyException("Cached result inconsistent with DB state")

        wallet = await self._get_locked_wallet(user_id)
        # Serialize responsible-play checks with wagers by locking the wallet first.
        from app.services.responsible_play_service import ResponsiblePlayService
        await ResponsiblePlayService(self._db).validate_wager_allowed(
            user_id,
            amount_paise,
            idempotency_key=idempotency_key,
        )
        available = wallet.balance - wallet.locked_balance

        validate_sufficient_balance(available, amount_paise)

        balance_before = wallet.balance
        wallet.locked_balance += amount_paise
        self._db.add(wallet)
        await self._db.flush()

        tx = await self._write_tx(
            wallet,
            idem_key=idempotency_key,
            tx_type=TransactionType.BET,
            amount=-amount_paise,  # negative: credits leave available pool
            balance_before=balance_before,
            balance_after=wallet.balance,
            reference=reference,
            description=description or f"Bet placed: {format_credits(amount_paise)}",
        )
        await self._db.commit()

        await store_idempotency_result(idempotency_key, payload, {"tx_id": tx.id})
        logger.info("Bet placed", user_id=user_id, amount=amount_paise, tx_id=tx.id)
        return tx

    # ------------------------------------------------------------------
    # settle_win: locked → credited (win amount added on top)
    # ------------------------------------------------------------------

    async def settle_win(
        self,
        user_id: str,
        bet_amount_paise: int,
        win_amount_paise: int,
        idempotency_key: str,
        reference: Optional[str] = None,
        description: Optional[str] = None,
    ) -> WalletTransaction:
        """Settle a winning wager.

        Removes the bet from locked_balance and credits (bet + win) back to
        the available balance.  Net gain = win_amount_paise.
        """
        validate_positive_paise(bet_amount_paise, "bet amount")
        if win_amount_paise < 0:
            raise BadRequestException("Win amount cannot be negative")
        if win_amount_paise > 0:
            validate_transaction_limit(win_amount_paise, "win amount")

        payload = {
            "user_id": user_id,
            "bet": bet_amount_paise,
            "win": win_amount_paise,
            "reference": reference,
        }
        cached = await check_idempotency(idempotency_key, payload)
        if cached is not None:
            existing = await self._repo.get_transaction_by_idempotency_key(idempotency_key)
            if existing:
                return existing
            raise IdempotencyException("Cached result inconsistent with DB state")

        wallet = await self._get_locked_wallet(user_id)

        if wallet.locked_balance < bet_amount_paise:
            raise BadRequestException(
                f"Cannot settle win: locked balance {wallet.locked_balance} < "
                f"bet amount {bet_amount_paise}"
            )

        balance_before = wallet.balance
        wallet.locked_balance -= bet_amount_paise
        wallet.balance += win_amount_paise  # net gain
        self._db.add(wallet)
        await self._db.flush()

        tx = await self._write_tx(
            wallet,
            idem_key=idempotency_key,
            tx_type=TransactionType.WIN,
            amount=win_amount_paise,
            balance_before=balance_before,
            balance_after=wallet.balance,
            reference=reference,
            description=description or f"Win: {format_credits(win_amount_paise)}",
        )
        await self._db.commit()

        await store_idempotency_result(idempotency_key, payload, {"tx_id": tx.id})
        logger.info("Win settled", user_id=user_id, win=win_amount_paise, tx_id=tx.id)
        return tx

    # ------------------------------------------------------------------
    # settle_loss: release locked (balance already reduced at place_bet)
    # ------------------------------------------------------------------

    async def settle_loss(
        self,
        user_id: str,
        bet_amount_paise: int,
        idempotency_key: str,
        reference: Optional[str] = None,
        description: Optional[str] = None,
    ) -> WalletTransaction:
        """Settle a losing wager.

        The bet was already deducted from available when placed.  Here we
        permanently deduct it from balance (remove locked portion) and write
        the ledger row.
        """
        validate_positive_paise(bet_amount_paise, "bet amount")

        payload = {"user_id": user_id, "amount": bet_amount_paise, "reference": reference}
        cached = await check_idempotency(idempotency_key, payload)
        if cached is not None:
            existing = await self._repo.get_transaction_by_idempotency_key(idempotency_key)
            if existing:
                return existing
            raise IdempotencyException("Cached result inconsistent with DB state")

        wallet = await self._get_locked_wallet(user_id)

        if wallet.locked_balance < bet_amount_paise:
            raise BadRequestException(
                f"Cannot settle loss: locked {wallet.locked_balance} < bet {bet_amount_paise}"
            )

        balance_before = wallet.balance
        wallet.locked_balance -= bet_amount_paise
        wallet.balance -= bet_amount_paise
        self._db.add(wallet)
        await self._db.flush()

        tx = await self._write_tx(
            wallet,
            idem_key=idempotency_key,
            tx_type=TransactionType.BET,
            amount=-bet_amount_paise,
            balance_before=balance_before,
            balance_after=wallet.balance,
            reference=reference,
            description=description or f"Loss: {format_credits(bet_amount_paise)}",
        )
        await self._db.commit()

        await store_idempotency_result(idempotency_key, payload, {"tx_id": tx.id})
        logger.info("Loss settled", user_id=user_id, amount=bet_amount_paise, tx_id=tx.id)
        return tx

    # ------------------------------------------------------------------
    # refund: release locked + restore available
    # ------------------------------------------------------------------

    async def refund(
        self,
        user_id: str,
        amount_paise: int,
        idempotency_key: str,
        reference: Optional[str] = None,
        description: Optional[str] = None,
    ) -> WalletTransaction:
        """Refund a bet (e.g., cancelled round).

        Removes amount from locked_balance (available was never truly deducted
        from balance, so balance stays the same — locked just decreases).
        """
        validate_positive_paise(amount_paise, "refund amount")

        payload = {"user_id": user_id, "amount": amount_paise, "reference": reference}
        cached = await check_idempotency(idempotency_key, payload)
        if cached is not None:
            existing = await self._repo.get_transaction_by_idempotency_key(idempotency_key)
            if existing:
                return existing
            raise IdempotencyException("Cached result inconsistent with DB state")

        wallet = await self._get_locked_wallet(user_id)

        if wallet.locked_balance < amount_paise:
            raise BadRequestException(
                f"Cannot refund: locked {wallet.locked_balance} < refund {amount_paise}"
            )

        balance_before = wallet.balance
        wallet.locked_balance -= amount_paise
        # balance stays the same — we're just releasing the lock
        self._db.add(wallet)
        await self._db.flush()

        tx = await self._write_tx(
            wallet,
            idem_key=idempotency_key,
            tx_type=TransactionType.REFUND,
            amount=amount_paise,
            balance_before=balance_before,
            balance_after=wallet.balance,
            reference=reference,
            description=description or f"Refund: {format_credits(amount_paise)}",
        )
        await self._db.commit()

        await store_idempotency_result(idempotency_key, payload, {"tx_id": tx.id})
        logger.info("Refund issued", user_id=user_id, amount=amount_paise, tx_id=tx.id)
        return tx

    # ------------------------------------------------------------------
    # credit_bonus: add credits to available balance
    # ------------------------------------------------------------------

    async def credit_bonus(
        self,
        user_id: str,
        amount_paise: int,
        idempotency_key: str,
        reference: Optional[str] = None,
        description: Optional[str] = None,
        tx_type: TransactionType = TransactionType.BONUS,
    ) -> WalletTransaction:
        """Credit virtual credits (bonus, faucet, admin grant)."""
        validate_transaction_limit(amount_paise, "bonus amount")

        payload = {"user_id": user_id, "amount": amount_paise, "reference": reference}
        cached = await check_idempotency(idempotency_key, payload)
        if cached is not None:
            existing = await self._repo.get_transaction_by_idempotency_key(idempotency_key)
            if existing:
                return existing
            raise IdempotencyException("Cached result inconsistent with DB state")

        wallet = await self._get_locked_wallet(user_id)
        balance_before = wallet.balance
        wallet.balance += amount_paise
        self._db.add(wallet)
        await self._db.flush()

        tx = await self._write_tx(
            wallet,
            idem_key=idempotency_key,
            tx_type=tx_type,
            amount=amount_paise,
            balance_before=balance_before,
            balance_after=wallet.balance,
            reference=reference,
            description=description or f"Credit: {format_credits(amount_paise)}",
        )
        await self._db.commit()

        await store_idempotency_result(idempotency_key, payload, {"tx_id": tx.id})
        logger.info("Bonus credited", user_id=user_id, amount=amount_paise, tx_id=tx.id)
        return tx

    # ------------------------------------------------------------------
    # daily_claim: delegate to DailyCreditService
    # ------------------------------------------------------------------

    async def daily_claim(
        self,
        user_id: str,
        idempotency_key: str,
    ) -> WalletTransaction:
        """Claim the daily virtual-credit faucet. Delegates to DailyCreditService."""
        from app.services.daily_credit_service import DailyCreditService

        svc = DailyCreditService(self._db)
        return await svc.claim(user_id, idempotency_key)

    # ------------------------------------------------------------------
    # admin_adjust: requires reason + writes audit log
    # ------------------------------------------------------------------

    async def admin_adjust(
        self,
        actor_id: str,
        target_user_id: str,
        amount_paise: int,
        reason: str,
        idempotency_key: str,
        ip_address: Optional[str] = None,
    ) -> WalletTransaction:
        """Admin-initiated balance adjustment (positive = credit, negative = debit).

        Writes both a WalletTransaction and an AuditLog row.
        Requires a non-empty reason string.
        """
        if not reason or not reason.strip():
            raise BadRequestException("Admin adjustment requires a non-empty reason")

        if amount_paise == 0:
            raise BadRequestException("Adjustment amount must be non-zero")

        payload = {
            "actor": actor_id,
            "target": target_user_id,
            "amount": amount_paise,
            "reason": reason,
        }
        cached = await check_idempotency(idempotency_key, payload)
        if cached is not None:
            existing = await self._repo.get_transaction_by_idempotency_key(idempotency_key)
            if existing:
                return existing
            raise IdempotencyException("Cached result inconsistent with DB state")

        wallet = await self._get_locked_wallet(target_user_id)
        balance_before = wallet.balance

        if amount_paise > 0:
            wallet.balance += amount_paise
        else:
            debit = abs(amount_paise)
            available = wallet.balance - wallet.locked_balance
            if debit > available:
                raise InsufficientBalanceException(
                    f"Admin debit {format_credits(debit)} exceeds available "
                    f"{format_credits(available)}"
                )
            wallet.balance -= debit

        self._db.add(wallet)
        await self._db.flush()

        tx = await self._write_tx(
            wallet,
            idem_key=idempotency_key,
            tx_type=TransactionType.ADJUSTMENT,
            amount=amount_paise,
            balance_before=balance_before,
            balance_after=wallet.balance,
            reference=f"ADMIN:{actor_id}",
            description=reason,
        )

        # Audit log (immutable record of who did what)
        audit = AuditLog(
            id=str(uuid.uuid4()),
            actor_id=actor_id,
            action="WALLET_ADJUST",
            target_type="wallet",
            target_id=wallet.id,
            details={
                "amount_paise": amount_paise,
                "balance_before": balance_before,
                "balance_after": wallet.balance,
                "reason": reason,
                "tx_id": tx.id,
            },
            ip_address=ip_address,
        )
        self._db.add(audit)
        await self._db.flush()
        await self._db.commit()

        await store_idempotency_result(idempotency_key, payload, {"tx_id": tx.id})
        logger.info(
            "Admin adjustment",
            actor=actor_id,
            target=target_user_id,
            amount=amount_paise,
            tx_id=tx.id,
        )
        return tx
