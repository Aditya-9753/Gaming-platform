"""The partner wallet ledger: the only code that writes aff_wallet_transactions.

Every entry: lock the wallet row (SELECT ... FOR UPDATE), append an entry with
the bucket's balance after the move, update the cached balance, all in the
caller's transaction. Entries are idempotent on ``idempotency_key``: posting the
same key twice returns the first entry and moves nothing.

Buckets
-------
PENDING    commission of the open period / CPA under hold (may be negative)
AVAILABLE  settled commission - withdrawals (may be negative under revshare carryover)
RESERVED   locked by open withdrawals (never negative)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate.constants import ZERO, Bucket, Direction, LedgerType, RiskSeverity
from app.affiliate.common import risk_event
from app.affiliate.util import money
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.affiliate import AffWallet, AffWalletTransaction

_FIELD = {
    Bucket.PENDING: "pending_balance",
    Bucket.AVAILABLE: "available_balance",
    Bucket.RESERVED: "reserved_balance",
}


async def lock_wallet(db: AsyncSession, partner_id: int) -> AffWallet:
    wallet = (
        await db.execute(select(AffWallet).where(AffWallet.partner_id == partner_id).with_for_update())
    ).scalar_one_or_none()
    if wallet is None:
        raise NotFoundException("Partner wallet not found")
    return wallet


async def get_wallet(db: AsyncSession, partner_id: int) -> AffWallet:
    wallet = (await db.execute(select(AffWallet).where(AffWallet.partner_id == partner_id))).scalar_one_or_none()
    if wallet is None:
        raise NotFoundException("Partner wallet not found")
    return wallet


async def _existing(db: AsyncSession, key: str) -> Optional[AffWalletTransaction]:
    return (
        await db.execute(select(AffWalletTransaction).where(AffWalletTransaction.idempotency_key == key))
    ).scalar_one_or_none()


async def post(
    db: AsyncSession,
    wallet: AffWallet,
    *,
    entry_type: LedgerType,
    bucket: Bucket,
    delta: Decimal,
    key: str,
    reference_type: Optional[str] = None,
    reference_id: Optional[object] = None,
    description: Optional[str] = None,
    created_by: Optional[str] = None,
) -> Optional[AffWalletTransaction]:
    """Move ``delta`` (signed) into ``bucket``. Zero moves nothing and returns None.

    The caller must hold the wallet lock (see ``lock_wallet``).
    """
    delta = money(delta)
    if delta == ZERO:
        return None
    previous = await _existing(db, key)
    if previous is not None:
        return previous
    attr = _FIELD[bucket]
    after = money(getattr(wallet, attr) or ZERO) + delta
    if bucket == Bucket.RESERVED and after < ZERO:
        raise BadRequestException("Reserved balance cannot go negative")
    setattr(wallet, attr, after)
    wallet.version = (wallet.version or 0) + 1
    entry = AffWalletTransaction(
        wallet_id=wallet.id,
        type=entry_type,
        bucket=bucket,
        direction=Direction.CREDIT if delta > 0 else Direction.DEBIT,
        amount=abs(delta),
        balance_after=after,
        reference_type=reference_type,
        reference_id=None if reference_id is None else str(reference_id),
        description=(description or "")[:255] or None,
        idempotency_key=key,
        created_by=created_by,
    )
    db.add(entry)
    await db.flush()
    return entry


async def move(
    db: AsyncSession,
    wallet: AffWallet,
    *,
    entry_type: LedgerType,
    source: Bucket,
    target: Bucket,
    amount: Decimal,
    key: str,
    reference_type: Optional[str] = None,
    reference_id: Optional[object] = None,
    description: Optional[str] = None,
    created_by: Optional[str] = None,
) -> None:
    """Transfer ``amount`` (signed) from one bucket to another as two linked entries."""
    common = dict(
        entry_type=entry_type,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
        created_by=created_by,
    )
    await post(db, wallet, bucket=source, delta=-money(amount), key=f"{key}:out", **common)
    await post(db, wallet, bucket=target, delta=money(amount), key=f"{key}:in", **common)


async def ledger_sums(db: AsyncSession, wallet_id: Optional[int] = None) -> Dict[int, Dict[Bucket, Decimal]]:
    """Recompute bucket balances from the ledger (wallet_id -> bucket -> sum)."""
    signed = func.sum(
        case(
            (AffWalletTransaction.direction == Direction.CREDIT, AffWalletTransaction.amount),
            else_=-AffWalletTransaction.amount,
        )
    )
    query = select(AffWalletTransaction.wallet_id, AffWalletTransaction.bucket, signed).group_by(
        AffWalletTransaction.wallet_id, AffWalletTransaction.bucket
    )
    if wallet_id is not None:
        query = query.where(AffWalletTransaction.wallet_id == wallet_id)
    out: Dict[int, Dict[Bucket, Decimal]] = {}
    for wid, bucket, total in (await db.execute(query)).all():
        bucket = bucket if isinstance(bucket, Bucket) else Bucket(bucket)
        out.setdefault(wid, {})[bucket] = money(total or 0)
    return out


async def reconcile(db: AsyncSession) -> List[Dict[str, object]]:
    """Nightly check: ledger sums must equal the cached wallet balances.

    Mismatches raise a HIGH risk event (the wallet is not changed automatically).
    """
    sums = await ledger_sums(db)
    mismatches: List[Dict[str, object]] = []
    for wallet in (await db.execute(select(AffWallet))).scalars().all():
        per_bucket = sums.get(wallet.id, {})
        for bucket, attr in _FIELD.items():
            cached = money(getattr(wallet, attr) or 0)
            ledger = per_bucket.get(bucket, ZERO)
            if cached != ledger:
                mismatches.append({"wallet_id": wallet.id, "partner_id": wallet.partner_id, "bucket": bucket.value,
                                   "cached": str(cached), "ledger": str(ledger)})
    for item in mismatches:
        await risk_event(
            db,
            "LEDGER_MISMATCH",
            RiskSeverity.HIGH,
            f"Wallet {item['wallet_id']} {item['bucket']} cache {item['cached']} != ledger {item['ledger']}",
            partner_id=int(item["partner_id"]),
            score=100,
            meta=item,
            dedupe_key=f"ledger-mismatch:{item['wallet_id']}:{item['bucket']}:{item['ledger']}:{item['cached']}",
        )
    return mismatches
