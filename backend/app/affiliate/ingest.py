"""Operator -> affiliate event ingestion (PRD §6).

Every event is stored raw in ``aff_ingest_events`` first (committed), then
processed. Failures stay visible (status FAILED, error, attempts) and are
retried by the worker and from the admin Ingest monitor. Duplicates return the
existing record instead of creating a second one.

Signature: ``X-Timestamp: <unix seconds>`` and
``X-Signature: hex(HMAC-SHA256(secret, "<timestamp>.<raw body>"))``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate import commission as commission_engine
from app.affiliate import postbacks
from app.affiliate import settings as aff_settings
from app.affiliate.common import Actor, audit
from app.affiliate.constants import (
    ZERO,
    CustomerStatus,
    DepositStatus,
    IngestEventType,
    IngestStatus,
    PeriodStatus,
    PostbackEvent,
)
from app.affiliate.tracking import attribute
from app.affiliate.util import aware, money, utcnow
from app.core.config import get_settings
from app.core.exceptions import BadRequestException, NotFoundException, UnauthorizedException
from app.core.logging import get_logger
from app.models.affiliate import (
    AffCustomer,
    AffDeposit,
    AffFxRate,
    AffIngestEvent,
    AffPlayerRevenueDaily,
    AffRegistration,
    AffReversal,
)

logger = get_logger("aff_ingest")

MAX_ATTEMPTS = 8


class IngestError(Exception):
    """Processing failed; the event is kept as FAILED (retryable unless permanent)."""

    def __init__(self, message: str, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


class MissingFxRate(IngestError):
    """No stored rate for the currency yet: fetch the reference rates and retry."""


# ---------------------------------------------------------------------------
# Signature
# ---------------------------------------------------------------------------


def sign(body: bytes, timestamp: int, secret: str) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, timestamp: Optional[str], signature: Optional[str]) -> None:
    settings = get_settings()
    secret = settings.AFFILIATE_INGEST_SECRET
    if not secret:
        raise UnauthorizedException("Ingest is not configured (AFFILIATE_INGEST_SECRET)")
    if not timestamp or not signature:
        raise UnauthorizedException("Missing X-Timestamp / X-Signature")
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise UnauthorizedException("Bad X-Timestamp") from exc
    if abs(time.time() - ts) > settings.AFFILIATE_INGEST_TOLERANCE_SECONDS:
        raise UnauthorizedException("Request timestamp is too old or in the future")
    expected = sign(body, ts, secret)
    if not hmac.compare_digest(expected, signature.strip().lower()):
        raise UnauthorizedException("Invalid signature")


# ---------------------------------------------------------------------------
# FX
# ---------------------------------------------------------------------------


async def fx_rate(db: AsyncSession, currency: str, on: date) -> Decimal:
    currency = currency.upper()
    if currency == "USD":
        return Decimal("1")
    row = (
        await db.execute(
            select(AffFxRate)
            .where(AffFxRate.currency == currency, AffFxRate.rate_date <= on)
            .order_by(AffFxRate.rate_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is not None:
        return Decimal(row.rate_to_usd)
    fallback = (await aff_settings.get(db, "fallback_fx_rates")) or {}
    if currency in fallback:
        return Decimal(str(fallback[currency]))
    raise MissingFxRate(f"No FX rate for {currency} on {on} (add it in Admin → Deals & Plans → FX rates)")


async def to_usd(db: AsyncSession, amount: Any, currency: str, on: date) -> Tuple[Decimal, Decimal]:
    rate = await fx_rate(db, currency, on)
    return money(money(amount) * rate), rate


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _ts(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        return aware(value)
    if value in (None, ""):
        raise IngestError(f"{field} is required", permanent=True)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise IngestError(f"{field} must be an ISO-8601 timestamp", permanent=True) from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _day(value: Any, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise IngestError(f"{field} must be YYYY-MM-DD", permanent=True) from exc


def _req(payload: Dict[str, Any], field: str, max_len: int = 64) -> str:
    value = str(payload.get(field) or "").strip()
    if not value:
        raise IngestError(f"{field} is required", permanent=True)
    if len(value) > max_len:
        raise IngestError(f"{field} is too long", permanent=True)
    return value


def _country(value: Any) -> Optional[str]:
    text = str(value or "").strip().upper()
    return text if len(text) == 2 and text.isalpha() else None


def idempotency_key(event_type: IngestEventType, payload: Dict[str, Any]) -> str:
    if event_type == IngestEventType.REGISTRATION:
        return _req(payload, "external_customer_id")
    if event_type == IngestEventType.DEPOSIT:
        # a deposit's status changes (PENDING -> COMPLETED) are separate events
        return f"{_req(payload, 'external_transaction_id')}:{str(payload.get('status') or 'COMPLETED').upper()}"
    if event_type == IngestEventType.REVERSAL:
        return _req(payload, "external_reversal_id")
    body = json.dumps(payload, sort_keys=True, default=str).encode()
    return "batch:" + hashlib.sha256(body).hexdigest()


# ---------------------------------------------------------------------------
# Receive / process
# ---------------------------------------------------------------------------


async def receive(
    db: AsyncSession, event_type: IngestEventType, payload: Dict[str, Any], *, source: str = "S2S", signature_ok: bool = True,
) -> Tuple[AffIngestEvent, bool]:
    """Store the event (or find its duplicate) and process it. Returns (event, duplicate)."""
    try:
        key = idempotency_key(event_type, payload)
    except IngestError as exc:
        raise BadRequestException(str(exc)) from exc
    existing = (
        await db.execute(
            select(AffIngestEvent).where(AffIngestEvent.event_type == event_type, AffIngestEvent.idempotency_key == key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.status == IngestStatus.FAILED:
            await process(db, existing)
        return existing, True
    event = AffIngestEvent(event_type=event_type, idempotency_key=key, payload=payload, source=source,
                           signature_ok=signature_ok, status=IngestStatus.RECEIVED)
    try:
        db.add(event)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(AffIngestEvent).where(AffIngestEvent.event_type == event_type, AffIngestEvent.idempotency_key == key)
            )
        ).scalar_one()
        return existing, True
    await process(db, event)
    return event, False


_HANDLERS: Dict[IngestEventType, Any] = {}


async def process(db: AsyncSession, event: AffIngestEvent) -> AffIngestEvent:
    """Run the handler in its own transaction; record the outcome on the event. Commits."""
    event_id = event.id
    handler = _HANDLERS[IngestEventType(event.event_type)]
    try:
        result_ref = await handler(db, event.payload)
        event = await db.get(AffIngestEvent, event_id)
        event.status = IngestStatus.IGNORED if result_ref == "ignored" else IngestStatus.PROCESSED
        event.result_ref = None if result_ref == "ignored" else (str(result_ref) if result_ref is not None else None)
        event.error = None
        event.attempts = (event.attempts or 0) + 1
        event.processed_at = utcnow()
        await db.commit()
    except Exception as exc:
        await db.rollback()
        event = await db.get(AffIngestEvent, event_id)
        event.attempts = (event.attempts or 0) + 1
        permanent = isinstance(exc, IngestError) and exc.permanent
        event.status = IngestStatus.FAILED
        event.error = (("permanent: " if permanent else "") + str(exc))[:2000]
        if permanent:
            event.attempts = max(event.attempts, MAX_ATTEMPTS)
        await db.commit()
        if not isinstance(exc, IngestError):
            logger.error("Ingest processing crashed", event_id=event_id, error=str(exc))
        if isinstance(exc, MissingFxRate) and get_settings().AFFILIATE_FX_AUTO_FETCH:
            from app.affiliate import fx

            if await fx.sync_if_due(db):  # throttled, so this retries at most once
                return await process(db, event)
    return event


async def retry_failed(db: AsyncSession, limit: int = 200) -> int:
    events = (
        await db.execute(
            select(AffIngestEvent)
            .where(AffIngestEvent.status == IngestStatus.FAILED, AffIngestEvent.attempts < MAX_ATTEMPTS)
            .order_by(AffIngestEvent.received_at)
            .limit(limit)
        )
    ).scalars().all()
    for event in events:
        await process(db, event)
    return len(events)


async def retry_one(db: AsyncSession, actor: Actor, event_id: int) -> AffIngestEvent:
    event = await db.get(AffIngestEvent, event_id)
    if event is None:
        raise NotFoundException("Ingest event not found")
    if event.status not in (IngestStatus.FAILED, IngestStatus.IGNORED):
        raise BadRequestException("Only failed or ignored events can be retried")
    await audit(db, actor, "AFF_INGEST_RETRY", "aff_ingest_event", event_id)
    await db.commit()
    return await process(db, event)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _customer(db: AsyncSession, external_id: str, country: Optional[str] = None, create: bool = False) -> Optional[AffCustomer]:
    customer = (await db.execute(select(AffCustomer).where(AffCustomer.external_customer_id == external_id))).scalar_one_or_none()
    if customer is None and create:
        customer = AffCustomer(external_customer_id=external_id, country=country, status=CustomerStatus.ACTIVE)
        db.add(customer)
        await db.flush()
    return customer


async def handle_registration(db: AsyncSession, payload: Dict[str, Any]) -> Any:
    external_id = _req(payload, "external_customer_id")
    country = _country(payload.get("country"))
    registered_at = _ts(payload.get("registered_at") or utcnow().isoformat(), "registered_at")
    customer = await _customer(db, external_id, country, create=True)
    if country and not customer.country:
        customer.country = country
    existing = (await db.execute(select(AffRegistration).where(AffRegistration.customer_id == customer.id))).scalar_one_or_none()
    if existing is not None:  # attribution is frozen
        return existing.id
    found = await attribute(db, click_id=payload.get("click_id"), promo_code=payload.get("promo_code"), registered_at=registered_at)
    if found is None:
        await db.flush()
        return "ignored"
    subs = dict(found.subs)
    for key in subs:  # the product may pass sub-ids it received on the landing URL
        if not subs[key] and payload.get(key):
            subs[key] = str(payload[key])[:128]
    reg = AffRegistration(
        customer_id=customer.id, partner_id=found.partner_id, source_id=found.source_id, campaign_id=found.campaign_id,
        tracking_link_id=found.tracking_link_id, promo_code_id=found.promo_code_id, click_id=found.click_id,
        visitor_id=found.visitor_id, attribution_type=found.attribution_type, country=country,
        registered_at=registered_at, **subs,
    )
    db.add(reg)
    await db.flush()
    await postbacks.queue(db, found.partner_id, PostbackEvent.REGISTRATION, f"reg:{reg.id}",
                          {"click_id": found.click_id, "customer": customer.id, "amount": "", **subs})
    from app.affiliate import analytics

    await analytics.mark_dirty(db, found.partner_id, registered_at)
    return reg.id


async def handle_deposit(db: AsyncSession, payload: Dict[str, Any]) -> Any:
    external_id = _req(payload, "external_customer_id")
    tx_id = _req(payload, "external_transaction_id")
    status = DepositStatus(str(payload.get("status") or "COMPLETED").upper())
    currency = str(payload.get("currency") or "USD").upper()[:3]
    amount = money(payload.get("amount"))
    if amount < ZERO:
        raise IngestError("amount cannot be negative", permanent=True)
    completed_at = _ts(payload.get("completed_at"), "completed_at") if payload.get("completed_at") else utcnow()
    customer = await _customer(db, external_id)
    if customer is None:
        # the registration may still be on its way; retried later, permanently ignored after MAX_ATTEMPTS
        raise IngestError(f"Unknown customer {external_id}")
    reg = (await db.execute(select(AffRegistration).where(AffRegistration.customer_id == customer.id))).scalar_one_or_none()
    amount_usd, rate = await to_usd(db, amount, currency, completed_at.date())
    deposit = (await db.execute(select(AffDeposit).where(AffDeposit.external_transaction_id == tx_id))).scalar_one_or_none()
    previous_status = deposit.status if deposit else None
    if deposit is None:
        deposit = AffDeposit(
            customer_id=customer.id, partner_id=reg.partner_id if reg else None, external_transaction_id=tx_id,
            amount=amount, currency=currency, amount_usd=amount_usd, fx_rate=rate, status=status,
            completed_at=completed_at if status == DepositStatus.COMPLETED else None,
        )
        db.add(deposit)
    else:
        if deposit.customer_id != customer.id:
            raise IngestError("external_transaction_id belongs to another customer", permanent=True)
        if deposit.status == DepositStatus.REVERSED:
            return deposit.id
        deposit.status = status
        deposit.amount, deposit.currency, deposit.amount_usd, deposit.fx_rate = amount, currency, amount_usd, rate
        if status == DepositStatus.COMPLETED:
            deposit.completed_at = completed_at
    await db.flush()
    if status == DepositStatus.COMPLETED and previous_status != DepositStatus.COMPLETED:
        earlier = (
            await db.execute(
                select(AffDeposit.id).where(
                    AffDeposit.customer_id == customer.id, AffDeposit.status.in_([DepositStatus.COMPLETED, DepositStatus.REVERSED]),
                    AffDeposit.id != deposit.id, AffDeposit.is_first_deposit.is_(True),
                ).limit(1)
            )
        ).first()
        deposit.is_first_deposit = earlier is None
        await db.flush()
        if deposit.partner_id is not None:
            if deposit.is_first_deposit:
                await commission_engine.on_first_deposit(db, deposit)
            macros = {"click_id": reg.click_id if reg else None, "customer": customer.id, "amount": f"{amount_usd:.2f}",
                      **{f"sub{i}": getattr(reg, f"sub{i}") if reg else None for i in range(1, 6)}}
            if deposit.is_first_deposit:
                await postbacks.queue(db, deposit.partner_id, PostbackEvent.FTD, f"ftd:{deposit.id}", macros)
            await postbacks.queue(db, deposit.partner_id, PostbackEvent.DEPOSIT, f"dep:{deposit.id}", macros)
            from app.affiliate import analytics

            await analytics.mark_dirty(db, deposit.partner_id, completed_at)
    return deposit.id


async def handle_revenue(db: AsyncSession, payload: Dict[str, Any]) -> Any:
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise IngestError("rows must be a non-empty list", permanent=True)
    if len(rows) > 5000:
        raise IngestError("At most 5000 rows per batch", permanent=True)
    errors: List[str] = []
    changed: List[AffPlayerRevenueDaily] = []
    touched: Dict[int, date] = {}
    for index, item in enumerate(rows):
        try:
            changed_row = await _revenue_row(db, item)
            if changed_row is not None:
                changed.append(changed_row)
                if changed_row.partner_id is not None:
                    touched[changed_row.partner_id] = min(touched.get(changed_row.partner_id, changed_row.revenue_date), changed_row.revenue_date)
        except IngestError as exc:
            errors.append(f"row {index}: {exc}")
    await db.flush()
    await commission_engine.process_revenue_rows(db, changed)
    from app.affiliate import analytics

    for partner_id, first_day in touched.items():
        await analytics.mark_dirty(db, partner_id, datetime.combine(first_day, datetime.min.time(), tzinfo=timezone.utc))
    if errors:
        # rows that succeeded stay applied (upserts are idempotent); the batch is retried for the rest
        await db.commit()
        raise IngestError("; ".join(errors[:20]) + (f" (+{len(errors) - 20} more)" if len(errors) > 20 else ""))
    return f"rows:{len(rows)}"


async def _revenue_row(db: AsyncSession, item: Dict[str, Any]) -> Optional[AffPlayerRevenueDaily]:
    if not isinstance(item, dict):
        raise IngestError("row must be an object", permanent=True)
    external_id = _req(item, "external_customer_id")
    day = _day(item.get("date"), "date")
    currency = str(item.get("currency") or "USD").upper()[:3]
    customer = await _customer(db, external_id)
    if customer is None:
        return None  # not an affiliate player: nothing to pay on
    period = await commission_engine.containing_period(db, day)
    if period is not None and period.status != PeriodStatus.OPEN:
        raise IngestError(f"period {period.start_date}..{period.end_date} is closed", permanent=True)
    rate = await fx_rate(db, currency, day)
    fields = {}
    for name in ("bets", "wins", "bonuses", "fees", "chargebacks"):
        fields[name] = money(money(item.get(name) or 0) * rate)
    if item.get("ngr") not in (None, ""):
        ngr = money(money(item["ngr"]) * rate)
    else:
        ngr = fields["bets"] - fields["wins"] - fields["bonuses"] - fields["fees"] - fields["chargebacks"]
    reg = (await db.execute(select(AffRegistration).where(AffRegistration.customer_id == customer.id))).scalar_one_or_none()
    row = (
        await db.execute(
            select(AffPlayerRevenueDaily).where(
                AffPlayerRevenueDaily.customer_id == customer.id, AffPlayerRevenueDaily.revenue_date == day
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = AffPlayerRevenueDaily(customer_id=customer.id, revenue_date=day, currency="USD")
        db.add(row)
    elif all(money(getattr(row, k)) == v for k, v in fields.items()) and money(row.ngr) == ngr:
        return None  # unchanged
    for key, value in fields.items():
        setattr(row, key, value)
    row.ngr = ngr
    row.partner_id = reg.partner_id if reg else None
    row.period_id = period.id if period else None
    row.needs_commission = True
    await db.flush()
    return row


async def handle_reversal(db: AsyncSession, payload: Dict[str, Any]) -> Any:
    reversal_id = _req(payload, "external_reversal_id")
    tx_id = _req(payload, "external_transaction_id")
    deposit = (await db.execute(select(AffDeposit).where(AffDeposit.external_transaction_id == tx_id))).scalar_one_or_none()
    if deposit is None:
        raise IngestError(f"Unknown deposit {tx_id}")
    received_at = utcnow()
    amount = money(payload.get("amount") or deposit.amount)
    amount_usd, _rate = await to_usd(db, amount, deposit.currency, received_at.date())
    reason = str(payload.get("reason") or "chargeback")[:255]
    row = AffReversal(external_reversal_id=reversal_id, deposit_id=deposit.id, customer_id=deposit.customer_id,
                      amount_usd=amount_usd, reason=reason, received_at=received_at)
    db.add(row)
    if amount_usd >= money(deposit.amount_usd):
        deposit.status = DepositStatus.REVERSED
    await db.flush()
    if deposit.qualified_for_cpa:
        await commission_engine.reverse_cpa(db, deposit, reason)
    return row.id


_HANDLERS.update({
    IngestEventType.REGISTRATION: handle_registration,
    IngestEventType.DEPOSIT: handle_deposit,
    IngestEventType.REVENUE: handle_revenue,
    IngestEventType.REVERSAL: handle_reversal,
})


async def import_csv(db: AsyncSession, actor: Actor, event_type: IngestEventType, text: str) -> Dict[str, int]:
    """Fallback when the operator cannot push: CSV rows become ingest events (same pipeline)."""
    import csv
    import io

    from app.security.uploads import validate_csv_text

    reader = csv.DictReader(io.StringIO(validate_csv_text(text)))
    stats = {"rows": 0, "processed": 0, "duplicates": 0, "failed": 0}
    if event_type == IngestEventType.REVENUE:
        rows = [dict(r) for r in reader]
        stats["rows"] = len(rows)
        for start in range(0, len(rows), 1000):
            event, dup = await receive(db, event_type, {"rows": rows[start:start + 1000]}, source="CSV")
            stats["duplicates" if dup else ("failed" if event.status == IngestStatus.FAILED else "processed")] += 1
    else:
        for record in reader:
            stats["rows"] += 1
            payload = {k: v for k, v in record.items() if v not in (None, "")}
            try:
                event, dup = await receive(db, event_type, payload, source="CSV")
            except BadRequestException:
                stats["failed"] += 1
                continue
            stats["duplicates" if dup else ("failed" if event.status == IngestStatus.FAILED else "processed")] += 1
    await audit(db, actor, "AFF_INGEST_CSV", "aff_ingest_event", None, new={"type": event_type.value, **stats})
    await db.commit()
    return stats
