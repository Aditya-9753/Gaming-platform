"""Wallet repository — all DB queries that touch wallets/wallet_transactions.

Critical invariants enforced here:
- get_wallet_for_update uses SELECT … FOR UPDATE so the caller holds an
  exclusive row lock for the duration of the enclosing transaction.
- add_transaction flushes immediately so the balance is visible to any
  subsequent queries in the same session before commit.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wallet import Wallet, WalletTransaction


class WalletRepository:
    """Data-access layer for Wallet and WalletTransaction.

    Never contains business logic — only SQL / ORM I/O.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    # ------------------------------------------------------------------
    # Wallet reads
    # ------------------------------------------------------------------

    async def get_by_user_id(self, user_id: str) -> Optional[Wallet]:
        """Read-only wallet fetch (no lock)."""
        result = await self._db.execute(
            select(Wallet).where(Wallet.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_wallet_for_update(self, user_id: str) -> Optional[Wallet]:
        """Return the wallet with an exclusive row-level lock.

        MUST be called inside an open transaction.  Every credit movement
        (bet, win, refund, …) must acquire this lock before touching balances
        to prevent race conditions / overdraw.
        """
        result = await self._db.execute(
            select(Wallet)
            .where(Wallet.user_id == user_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_wallet_id(self, wallet_id: str) -> Optional[Wallet]:
        result = await self._db.execute(
            select(Wallet).where(Wallet.id == wallet_id)
        )
        return result.scalar_one_or_none()

    async def get_by_wallet_id_for_update(self, wallet_id: str) -> Optional[Wallet]:
        result = await self._db.execute(
            select(Wallet).where(Wallet.id == wallet_id).with_for_update()
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Wallet writes (caller handles commit / rollback)
    # ------------------------------------------------------------------

    async def create(self, wallet: Wallet) -> Wallet:
        self._db.add(wallet)
        await self._db.flush()
        await self._db.refresh(wallet)
        return wallet

    async def save(self, wallet: Wallet) -> Wallet:
        self._db.add(wallet)
        await self._db.flush()
        await self._db.refresh(wallet)
        return wallet

    # ------------------------------------------------------------------
    # Transaction ledger
    # ------------------------------------------------------------------

    async def add_transaction(self, tx: WalletTransaction) -> WalletTransaction:
        """Append an immutable ledger row and flush to the DB."""
        self._db.add(tx)
        await self._db.flush()
        return tx

    async def get_transaction_by_idempotency_key(
        self, key: str
    ) -> Optional[WalletTransaction]:
        result = await self._db.execute(
            select(WalletTransaction).where(WalletTransaction.idempotency_key == key)
        )
        return result.scalar_one_or_none()

    async def get_transactions(
        self,
        wallet_id: str,
        *,
        tx_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[Sequence[WalletTransaction], int]:
        """Paginated, optionally-filtered transaction history.

        Returns (rows, total_count).
        """
        base_q = select(WalletTransaction).where(
            WalletTransaction.wallet_id == wallet_id
        )
        count_q = select(func.count()).select_from(WalletTransaction).where(
            WalletTransaction.wallet_id == wallet_id
        )

        if tx_type:
            base_q = base_q.where(WalletTransaction.type == tx_type)
            count_q = count_q.where(WalletTransaction.type == tx_type)

        total_result = await self._db.execute(count_q)
        total = total_result.scalar_one()

        rows_result = await self._db.execute(
            base_q.order_by(WalletTransaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return rows_result.scalars().all(), total

    async def ledger_sum(self, wallet_id: str) -> int:
        """Return the algebraic sum of all completed credit movements.

        Used in integrity assertions: ledger_sum must equal wallet.balance.
        """
        from app.core.constants import TransactionStatus

        # BET and locked movements use negative amounts in the ledger
        # (balance_after - balance_before captures the net effect per row)
        result = await self._db.execute(
            select(func.coalesce(func.sum(WalletTransaction.amount), 0))
            .where(
                WalletTransaction.wallet_id == wallet_id,
                WalletTransaction.status == TransactionStatus.COMPLETED.value,
            )
        )
        return result.scalar_one()
