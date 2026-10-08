"""Rudra247 as the operator: report its own players to the affiliate platform.

The same events an external operator would push over S2S are written as
``aff_ingest_events`` rows (source INTERNAL) *inside the operator's own
transaction* — a transactional outbox: a credited deposit and its affiliate
event commit together or not at all. The worker then processes RECEIVED events
through the normal ingest pipeline.

Amounts: Rudra247 keeps integer paise of INR; events carry rupees + "INR" and
the ingest converts to USD with the stored / fallback FX rate.
"""

from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate.constants import IngestEventType, IngestStatus
from app.affiliate.ingest import idempotency_key, process, receive
from app.affiliate.util import utcnow
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.affiliate import AffCustomer, AffIngestEvent, AffRegistration

logger = get_logger("aff_operator_bridge")

CURRENCY = "INR"
_PAISE = Decimal(100)
_BONUS_TYPES = ("BONUS", "FAUCET")
_VOID_ENTRY_STATUSES = ("REFUNDED", "ABANDONED", "CANCELLED")


def enabled() -> bool:
    return bool(get_settings().AFFILIATE_INTERNAL_OPERATOR)


def _rupees(paise: int) -> str:
    return str((Decimal(int(paise or 0)) / _PAISE).quantize(Decimal("0.01")))


async def _outbox(db: AsyncSession, event_type: IngestEventType, payload: Dict[str, Any]) -> None:
    key = idempotency_key(event_type, payload)
    exists = (await db.execute(select(AffIngestEvent.id).where(
        AffIngestEvent.event_type == event_type, AffIngestEvent.idempotency_key == key))).first()
    if exists:
        return
    db.add(AffIngestEvent(event_type=event_type, idempotency_key=key, payload=payload, source="INTERNAL",
                          signature_ok=True, status=IngestStatus.RECEIVED))
    await db.flush()


async def _is_affiliate_player(db: AsyncSession, user_id: str) -> bool:
    return (await db.execute(select(AffIngestEvent.id).where(
        AffIngestEvent.event_type == IngestEventType.REGISTRATION, AffIngestEvent.idempotency_key == user_id))).first() is not None


async def player_registered(db: AsyncSession, user_id: str, *, click_id: Optional[str], promo_code: Optional[str],
                            country: Optional[str], registered_at: Optional[datetime] = None) -> None:
    """Called inside the sign-up transaction. Only referred players are reported."""
    if not enabled() or not (click_id or promo_code):
        return
    await _outbox(db, IngestEventType.REGISTRATION, {
        "external_customer_id": user_id, "click_id": (click_id or "").strip().upper()[:26] or None,
        "promo_code": (promo_code or "").strip().upper()[:32] or None, "country": country,
        "registered_at": (registered_at or utcnow()).isoformat(),
    })


async def deposit_credited(db: AsyncSession, user_id: str, deposit_id: str, amount_paise: int, credited_at: Optional[datetime]) -> None:
    if not enabled() or not await _is_affiliate_player(db, user_id):
        return
    await _outbox(db, IngestEventType.DEPOSIT, {
        "external_customer_id": user_id, "external_transaction_id": deposit_id, "amount": _rupees(amount_paise),
        "currency": CURRENCY, "status": "COMPLETED", "completed_at": (credited_at or utcnow()).isoformat(),
    })


async def deposit_reversed(db: AsyncSession, user_id: str, deposit_id: str, amount_paise: int, reason: str) -> None:
    if not enabled() or not await _is_affiliate_player(db, user_id):
        return
    await _outbox(db, IngestEventType.REVERSAL, {
        "external_reversal_id": f"rev:{deposit_id}", "external_transaction_id": deposit_id,
        "amount": _rupees(amount_paise), "reason": reason[:200],
    })


async def report_revenue(db: AsyncSession, day: date) -> Optional[int]:
    """Daily NGR per referred player: bets - wins - bonuses (rupees). Returns the ingest event id."""
    from app.models.game import GameEntry
    from app.models.wallet import Wallet, WalletTransaction

    if not enabled():
        return None
    start = datetime.combine(day, dtime.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    players = [row[0] for row in (await db.execute(
        select(AffCustomer.external_customer_id).join(AffRegistration, AffRegistration.customer_id == AffCustomer.id))).all()]
    if not players:
        return None
    rows: List[Dict[str, Any]] = []
    for chunk_start in range(0, len(players), 500):
        chunk = players[chunk_start:chunk_start + 500]
        bets = {uid: (b or 0, w or 0) for uid, b, w in (await db.execute(
            select(GameEntry.user_id, func.sum(GameEntry.bet_amount), func.sum(GameEntry.payout_amount))
            .where(GameEntry.user_id.in_(chunk), GameEntry.created_at >= start, GameEntry.created_at < end,
                   GameEntry.status.not_in(_VOID_ENTRY_STATUSES))
            .group_by(GameEntry.user_id))).all()}
        bonuses = {uid: total or 0 for uid, total in (await db.execute(
            select(Wallet.user_id, func.sum(WalletTransaction.amount))
            .join(Wallet, Wallet.id == WalletTransaction.wallet_id)
            .where(Wallet.user_id.in_(chunk), WalletTransaction.type.in_(_BONUS_TYPES),
                   WalletTransaction.created_at >= start, WalletTransaction.created_at < end)
            .group_by(Wallet.user_id))).all()}
        for uid in chunk:
            bet, won = bets.get(uid, (0, 0))
            bonus = bonuses.get(uid, 0)
            if not (bet or won or bonus):
                continue
            rows.append({"external_customer_id": uid, "date": day.isoformat(), "currency": CURRENCY,
                         "bets": _rupees(bet), "wins": _rupees(won), "bonuses": _rupees(bonus), "fees": "0", "chargebacks": "0"})
    if not rows:
        return None
    last_id = None
    for start_index in range(0, len(rows), 2000):
        event, _dup = await receive(db, IngestEventType.REVENUE, {"rows": rows[start_index:start_index + 2000]}, source="INTERNAL")
        last_id = event.id
    return last_id


async def process_outbox(db: AsyncSession, limit: int = 500) -> int:
    """Worker: process events written by the outbox (and anything else left RECEIVED)."""
    events = (await db.execute(
        select(AffIngestEvent).where(AffIngestEvent.status == IngestStatus.RECEIVED).order_by(AffIngestEvent.id).limit(limit)
    )).scalars().all()
    for event in events:
        await process(db, event)
    return len(events)


async def sync_today(db: AsyncSession) -> None:
    """Hourly: keep today's and yesterday's revenue fresh (upserts until the period closes)."""
    today = utcnow().date()
    for day in (today - timedelta(days=1), today):
        try:
            await report_revenue(db, day)
        except Exception as exc:
            await db.rollback()
            logger.error("Internal revenue report failed", day=str(day), error=str(exc))

