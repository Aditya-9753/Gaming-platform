"""Bonus promo codes.

New accounts get no automatic bonus (``signup_bonus_paise`` defaults to 0): a bonus only
comes from a promo code the super admin created. Each player can use a code once, a code
can be limited to a number of uses and an expiry date, and every credit is a normal BONUS
ledger row so wallet integrity checks keep balancing.

Callers own the transaction: nothing here commits.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TransactionStatus, TransactionType
from app.core.exceptions import BadRequestException, ConflictException, ForbiddenException, NotFoundException
from app.core.logging import get_logger
from app.models.promo import PromoCode, PromoRedemption
from app.models.wallet import WalletTransaction
from app.repositories.wallet_repo import WalletRepository

logger = get_logger("promo_service")

CODE_RE = re.compile(r"^[A-Z0-9_-]{3,32}$")


def normalize(code: str) -> str:
    return (code or "").strip().upper()


async def find(db: AsyncSession, code: str, *, lock: bool = False) -> Optional[PromoCode]:
    stmt = select(PromoCode).where(PromoCode.code == normalize(code))
    if lock:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


def unusable_reason(promo: PromoCode) -> Optional[str]:
    """Why nobody can redeem this code right now (None = it is usable)."""
    if not promo.is_active:
        return "This promo code is no longer active"
    if promo.expires_at is not None and promo.expires_at <= datetime.now(timezone.utc):
        return "This promo code has expired"
    if promo.max_uses is not None and promo.used_count >= promo.max_uses:
        return "This promo code has been fully used"
    return None


async def redeem(db: AsyncSession, user_id: str, code: str) -> Dict[str, Any]:
    """Credit the code's bonus to the player's wallet (once per player per code)."""
    promo = await find(db, code, lock=True)  # row lock: concurrent redemptions of one code queue up
    if promo is None:
        raise NotFoundException("This promo code is not valid")
    reason = unusable_reason(promo)
    if reason:
        raise BadRequestException(reason)
    already = (await db.execute(
        select(PromoRedemption.id).where(PromoRedemption.promo_code_id == promo.id, PromoRedemption.user_id == user_id)
    )).first()
    if already:
        raise ConflictException("You have already used this promo code")

    wallets = WalletRepository(db)
    wallet = await wallets.get_wallet_for_update(user_id)
    if wallet is None:
        raise NotFoundException("Wallet not found")
    if wallet.is_frozen:
        raise ForbiddenException("Wallet is frozen — contact support")

    before = wallet.balance
    wallet.balance += promo.amount_paise
    db.add(wallet)
    tx = await wallets.add_transaction(WalletTransaction(
        id=str(uuid.uuid4()),
        wallet_id=wallet.id,
        idempotency_key=f"promo:{promo.id}:{user_id}",
        type=TransactionType.BONUS.value,
        amount=promo.amount_paise,
        balance_before=before,
        balance_after=wallet.balance,
        status=TransactionStatus.COMPLETED.value,
        reference=f"PROMO:{promo.code}",
        description=f"Promo code {promo.code}",
    ))
    promo.used_count += 1
    db.add(PromoRedemption(id=str(uuid.uuid4()), promo_code_id=promo.id, user_id=user_id,
                           amount_paise=promo.amount_paise, transaction_id=tx.id))
    await db.flush()
    logger.info("Promo code redeemed", user_id=user_id, code=promo.code, amount=promo.amount_paise)
    return {"code": promo.code, "amount_paise": promo.amount_paise, "balance_after": wallet.balance}


def to_dict(promo: PromoCode) -> Dict[str, Any]:
    return {
        "id": promo.id,
        "code": promo.code,
        "amount_paise": promo.amount_paise,
        "max_uses": promo.max_uses,
        "used_count": promo.used_count,
        "expires_at": promo.expires_at.isoformat() if promo.expires_at else None,
        "is_active": promo.is_active,
        "note": promo.note,
        "status": "ACTIVE" if unusable_reason(promo) is None else ("PAUSED" if not promo.is_active else "ENDED"),
        "created_at": promo.created_at.isoformat() if promo.created_at else None,
    }
