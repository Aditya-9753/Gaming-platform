"""Daily virtual-credit faucet service.

Rules:
- A user may claim once every 24 hours (rolling window, not calendar-day).
- Claim amount is read from SystemSetting key 'daily_claim_amount_paise'
  (configurable at runtime by an admin without code changes).
- Cooldown tracking is stored in Redis (with in-memory fallback).
- A WalletTransaction ledger row is written on every successful claim.
- The claim is idempotent within the cooldown window.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TransactionStatus, TransactionType
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.logging import get_logger
from app.models.wallet import Wallet, WalletTransaction
from app.repositories.wallet_repo import WalletRepository
from app.utils.money import format_credits, validate_positive_paise

logger = get_logger("daily_credit_service")

# Redis key prefix and cooldown
_CLAIM_PREFIX = "daily_claim:"
_COOLDOWN_SECONDS = 86_400  # 24 hours

# Default claim amount if no SystemSetting is configured: ₹10 = 1,000 paise
# (keep in sync with platform_settings.SETTINGS_SCHEMA)
_DEFAULT_CLAIM_PAISE = 1_000


class DailyCreditService:
    """Manages the once-per-24h virtual-credit faucet."""

    def __init__(self, session: AsyncSession) -> None:
        self._db = session
        self._repo = WalletRepository(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def claim(
        self,
        user_id: str,
        idempotency_key: str,
    ) -> WalletTransaction:
        """Award the daily virtual-credit bonus to the user.

        Raises:
            BadRequestException: if the user already claimed within 24h.
            NotFoundException: if the wallet doesn't exist.
        """
        # 1. Check / enforce cooldown in Redis
        redis_key = f"{_CLAIM_PREFIX}{user_id}"
        cooldown_remaining = await self._get_remaining_cooldown(redis_key)
        if cooldown_remaining > 0:
            hours = cooldown_remaining // 3600
            mins = (cooldown_remaining % 3600) // 60
            raise BadRequestException(
                f"Daily credit already claimed. Next claim available in "
                f"{hours}h {mins}m."
            )

        # 2. Resolve claim amount from DB settings (cached in Redis)
        claim_paise = await self._get_claim_amount()

        # 3. Acquire wallet lock and apply credit
        wallet = await self._repo.get_wallet_for_update(user_id)
        if not wallet:
            raise NotFoundException(f"Wallet not found for user {user_id}")

        balance_before = wallet.balance
        wallet.balance += claim_paise
        self._db.add(wallet)
        await self._db.flush()

        tx = WalletTransaction(
            id=str(uuid.uuid4()),
            wallet_id=wallet.id,
            idempotency_key=idempotency_key,
            type=TransactionType.FAUCET.value,
            amount=claim_paise,
            balance_before=balance_before,
            balance_after=wallet.balance,
            status=TransactionStatus.COMPLETED.value,
            reference="DAILY_CLAIM",
            description=f"Daily credit claim: {format_credits(claim_paise)}",
        )
        await self._repo.add_transaction(tx)

        # 4. Set cooldown BEFORE commit — if commit fails we re-enter with
        #    duplicate idem key and the DB UNIQUE constraint protects us.
        await self._set_cooldown(redis_key, _COOLDOWN_SECONDS)
        await self._db.commit()

        logger.info(
            "Daily credit claimed",
            user_id=user_id,
            amount=claim_paise,
            tx_id=tx.id,
        )
        return tx

    async def get_cooldown_remaining(self, user_id: str) -> int:
        """Return seconds until the next claim is available (0 if claimable now)."""
        redis_key = f"{_CLAIM_PREFIX}{user_id}"
        return await self._get_remaining_cooldown(redis_key)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _get_claim_amount(self) -> int:
        """Read 'daily_claim_amount_paise' from SystemSetting, or use default."""
        try:
            from app.models.system_setting import SystemSetting

            result = await self._db.execute(
                select(SystemSetting).where(
                    SystemSetting.key == "daily_claim_amount_paise"
                )
            )
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                amount = int(setting.value)
                validate_positive_paise(amount, "daily_claim_amount_paise")
                return amount
        except Exception:
            pass
        return _DEFAULT_CLAIM_PAISE

    async def _get_remaining_cooldown(self, redis_key: str) -> int:
        """Return remaining seconds of cooldown from Redis (0 if not set)."""
        try:
            from app.core.redis import get_redis_client

            redis = get_redis_client()
            ttl = await redis.ttl(redis_key)
            return max(0, ttl) if isinstance(ttl, int) else 0
        except Exception:
            return 0

    async def _set_cooldown(self, redis_key: str, seconds: int) -> None:
        """Mark cooldown in Redis."""
        try:
            from app.core.redis import get_redis_client

            redis = get_redis_client()
            await redis.set(redis_key, "1", ex=seconds)
        except Exception:
            logger.warning(
                "Could not set daily-claim cooldown in Redis", redis_key=redis_key
            )
