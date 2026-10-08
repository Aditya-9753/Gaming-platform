"""Pre-aggregated statistics: aff_analytics_hourly / aff_analytics_daily.

Rows are rebuilt (delete + insert) for a time window from the raw tables, so a
rebuild is idempotent and late data simply means rebuilding older days. The
API never writes these tables; workers do:

* every few minutes: today (all partners) — clicks never mark anything dirty;
* events (registration, deposit, revenue, commission changes) mark
  ``partner -> earliest affected time`` dirty, and the worker rebuilds from there.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import and_, case, delete, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate.constants import ZERO, CommissionStatus, CommissionType, DepositStatus, RegistrationStatus
from app.affiliate.util import aware, money, utcnow
from app.core.logging import get_logger
from app.models.affiliate import (
    AffAnalyticsDaily,
    AffAnalyticsHourly,
    AffCommission,
    AffDeposit,
    AffPlayerRevenueDaily,
    AffRegistration,
    AffTrackingClick,
)

# Constants are inlined as SQL text: GROUP BY must repeat the SELECT expression exactly, and with
# bind parameters ($1 in SELECT, $4 in GROUP BY under asyncpg) PostgreSQL treats them as different.
ZERO_SQL = literal_column("0")
EMPTY_SQL = literal_column("''")

logger = get_logger("aff_analytics")

DIRTY_KEY = "aff:analytics_dirty"
_memory_dirty: Dict[int, str] = {}

Dims = Tuple[int, int, int, int, datetime, str]
_METRICS = ("clicks", "unique_clicks", "registrations", "first_deposits", "deposit_count",
            "deposit_amount", "ngr", "income", "sub_commission")


def _midnight(value: datetime) -> datetime:
    value = aware(value)
    return datetime.combine(value.date(), dtime.min, tzinfo=timezone.utc)


def _hour_expr(db: AsyncSession, column: Any) -> Any:
    if db.bind.dialect.name == "postgresql":
        return func.date_trunc(literal_column("'hour'"), func.timezone(literal_column("'UTC'"), column))
    return func.strftime(literal_column("'%Y-%m-%d %H:00:00'"), column)


def _parse_hour(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


async def mark_dirty(db: AsyncSession, partner_id: Optional[int], when: datetime) -> None:
    """Remember the earliest time whose stats must be rebuilt for this partner."""
    if partner_id is None:
        return
    stamp = _midnight(when).isoformat()
    try:
        from app.core.redis import get_redis_client

        redis = get_redis_client()
        current = await redis.hget(DIRTY_KEY, str(partner_id))
        if current is None or (current.decode() if isinstance(current, bytes) else current) > stamp:
            await redis.hset(DIRTY_KEY, str(partner_id), stamp)
        return
    except Exception:
        pass
    current = _memory_dirty.get(partner_id)
    if current is None or current > stamp:
        _memory_dirty[partner_id] = stamp


async def _pop_dirty() -> Dict[int, datetime]:
    items: Dict[int, str] = {}
    try:
        from app.core.redis import get_redis_client

        redis = get_redis_client()
        raw = await redis.hgetall(DIRTY_KEY)
        if raw:
            await redis.hdel(DIRTY_KEY, *raw.keys())
        items = {int(k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v) for k, v in raw.items()}
    except Exception:
        pass
    items.update({k: v for k, v in _memory_dirty.items() if k not in items or v < items[k]})
    _memory_dirty.clear()
    return {k: datetime.fromisoformat(v) for k, v in items.items()}


async def rebuild(
    db: AsyncSession, start: datetime, end: Optional[datetime] = None, partner_ids: Optional[Sequence[int]] = None
) -> int:
    """Recompute hourly + daily rows for [midnight(start), end). Commits. Returns hourly rows written."""
    start = _midnight(start)
    end = aware(end) if end else _midnight(utcnow()) + timedelta(days=1)
    if end <= start:
        return 0
    pids = list(partner_ids) if partner_ids else None
    buckets: Dict[Dims, Dict[str, Any]] = defaultdict(lambda: {m: (ZERO if m in ("deposit_amount", "ngr", "income", "sub_commission") else 0) for m in _METRICS})

    def pf(column: Any) -> List[Any]:
        return [column.in_(pids)] if pids else []

    # --- clicks (valid = not bot, not fraud)
    hour = _hour_expr(db, AffTrackingClick.clicked_at)
    query = (
        select(
            AffTrackingClick.partner_id, AffTrackingClick.source_id, func.coalesce(AffTrackingClick.campaign_id, ZERO_SQL),
            AffTrackingClick.tracking_link_id, hour, func.coalesce(AffTrackingClick.country, EMPTY_SQL),
            func.count(), func.sum(case((AffTrackingClick.is_unique.is_(True), 1), else_=0)),
        )
        .where(AffTrackingClick.clicked_at >= start, AffTrackingClick.clicked_at < end,
               AffTrackingClick.is_bot.is_(False), AffTrackingClick.is_fraud.is_(False), *pf(AffTrackingClick.partner_id))
        .group_by(AffTrackingClick.partner_id, AffTrackingClick.source_id, func.coalesce(AffTrackingClick.campaign_id, ZERO_SQL),
                  AffTrackingClick.tracking_link_id, hour, func.coalesce(AffTrackingClick.country, EMPTY_SQL))
    )
    for pid, sid, cid, lid, h, country, total, unique in (await db.execute(query)).all():
        row = buckets[(pid, sid, cid, lid, _parse_hour(h), country)]
        row["clicks"] += int(total or 0)
        row["unique_clicks"] += int(unique or 0)

    # --- registrations
    hour = _hour_expr(db, AffRegistration.registered_at)
    reg_dims = (AffRegistration.partner_id, func.coalesce(AffRegistration.source_id, ZERO_SQL), func.coalesce(AffRegistration.campaign_id, ZERO_SQL),
                func.coalesce(AffRegistration.tracking_link_id, ZERO_SQL))
    query = (
        select(*reg_dims, hour, func.coalesce(AffRegistration.country, EMPTY_SQL), func.count())
        .where(AffRegistration.registered_at >= start, AffRegistration.registered_at < end,
               AffRegistration.status == RegistrationStatus.ACTIVE, *pf(AffRegistration.partner_id))
        .group_by(*reg_dims, hour, func.coalesce(AffRegistration.country, EMPTY_SQL))
    )
    for pid, sid, cid, lid, h, country, total in (await db.execute(query)).all():
        buckets[(pid, sid, cid, lid, _parse_hour(h), country)]["registrations"] += int(total or 0)

    # --- deposits (dimensions come from the frozen registration)
    hour = _hour_expr(db, AffDeposit.completed_at)
    query = (
        select(*reg_dims, hour, func.coalesce(AffRegistration.country, EMPTY_SQL), func.count(), func.sum(AffDeposit.amount_usd),
               func.sum(case((AffDeposit.is_first_deposit.is_(True), 1), else_=0)))
        .join(AffRegistration, AffRegistration.customer_id == AffDeposit.customer_id)
        .where(AffDeposit.completed_at >= start, AffDeposit.completed_at < end, AffDeposit.status == DepositStatus.COMPLETED,
               AffDeposit.is_fraud.is_(False), *pf(AffRegistration.partner_id))
        .group_by(*reg_dims, hour, func.coalesce(AffRegistration.country, EMPTY_SQL))
    )
    for pid, sid, cid, lid, h, country, count, amount, ftd in (await db.execute(query)).all():
        row = buckets[(pid, sid, cid, lid, _parse_hour(h), country)]
        row["deposit_count"] += int(count or 0)
        row["deposit_amount"] += money(amount or 0)
        row["first_deposits"] += int(ftd or 0)

    # --- daily NGR (dated rows land on the day's 00:00 hour)
    query = (
        select(*reg_dims, AffPlayerRevenueDaily.revenue_date, func.coalesce(AffRegistration.country, EMPTY_SQL), func.sum(AffPlayerRevenueDaily.ngr))
        .join(AffRegistration, AffRegistration.customer_id == AffPlayerRevenueDaily.customer_id)
        .where(AffPlayerRevenueDaily.revenue_date >= start.date(), AffPlayerRevenueDaily.revenue_date < end.date(),
               *pf(AffRegistration.partner_id))
        .group_by(*reg_dims, AffPlayerRevenueDaily.revenue_date, func.coalesce(AffRegistration.country, EMPTY_SQL))
    )
    for pid, sid, cid, lid, day, country, ngr in (await db.execute(query)).all():
        h = datetime.combine(_as_date(day), dtime.min, tzinfo=timezone.utc)
        buckets[(pid, sid, cid, lid, h, country)]["ngr"] += money(ngr or 0)

    # --- commission income (CPA + revshare, by revenue date)
    query = (
        select(AffCommission.partner_id, func.coalesce(AffRegistration.source_id, ZERO_SQL), func.coalesce(AffRegistration.campaign_id, ZERO_SQL),
               func.coalesce(AffRegistration.tracking_link_id, ZERO_SQL), AffCommission.revenue_date,
               func.coalesce(AffRegistration.country, EMPTY_SQL), AffCommission.commission_type, func.sum(AffCommission.commission_amount))
        .outerjoin(AffRegistration, and_(AffRegistration.customer_id == AffCommission.customer_id, AffCommission.customer_id != 0))
        .where(AffCommission.revenue_date >= start.date(), AffCommission.revenue_date < end.date(),
               AffCommission.status != CommissionStatus.REVERSED, *pf(AffCommission.partner_id))
        .group_by(AffCommission.partner_id, func.coalesce(AffRegistration.source_id, ZERO_SQL), func.coalesce(AffRegistration.campaign_id, ZERO_SQL),
                  func.coalesce(AffRegistration.tracking_link_id, ZERO_SQL), AffCommission.revenue_date,
                  func.coalesce(AffRegistration.country, EMPTY_SQL), AffCommission.commission_type)
    )
    for pid, sid, cid, lid, day, country, ctype, amount in (await db.execute(query)).all():
        h = datetime.combine(_as_date(day), dtime.min, tzinfo=timezone.utc)
        ctype = CommissionType(ctype)
        key = "sub_commission" if ctype == CommissionType.SUBPARTNER else "income"
        buckets[(pid, sid, cid, lid, h, country)][key] += money(amount or 0)

    # --- write
    hourly_filter = [AffAnalyticsHourly.date_hour >= start, AffAnalyticsHourly.date_hour < end]
    daily_filter = [AffAnalyticsDaily.stat_date >= start.date(), AffAnalyticsDaily.stat_date < end.date()]
    if pids:
        hourly_filter.append(AffAnalyticsHourly.partner_id.in_(pids))
        daily_filter.append(AffAnalyticsDaily.partner_id.in_(pids))
    await db.execute(delete(AffAnalyticsHourly).where(*hourly_filter))
    await db.execute(delete(AffAnalyticsDaily).where(*daily_filter))

    daily: Dict[Tuple[int, int, int, int, date, str], Dict[str, Any]] = defaultdict(lambda: {m: 0 for m in _METRICS})
    written = 0
    for (pid, sid, cid, lid, h, country), metrics in buckets.items():
        if not any(metrics[m] for m in _METRICS):
            continue
        db.add(AffAnalyticsHourly(partner_id=pid, source_id=sid or 0, campaign_id=cid or 0, tracking_link_id=lid or 0,
                                  date_hour=h, country=country or "", **metrics))
        written += 1
        day_row = daily[(pid, sid or 0, cid or 0, lid or 0, h.date(), country or "")]
        for m in _METRICS:
            day_row[m] = day_row[m] + metrics[m]
    for (pid, sid, cid, lid, day, country), metrics in daily.items():
        db.add(AffAnalyticsDaily(partner_id=pid, source_id=sid, campaign_id=cid, tracking_link_id=lid, stat_date=day,
                                 country=country, **{m: (money(v) if m in ("deposit_amount", "ngr", "income", "sub_commission") else v)
                                                     for m, v in metrics.items()}))
    await db.commit()
    return written


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


async def rebuild_dirty(db: AsyncSession) -> int:
    dirty = await _pop_dirty()
    total = 0
    for partner_id, since in dirty.items():
        try:
            total += await rebuild(db, since, partner_ids=[partner_id])
        except Exception as exc:
            await db.rollback()
            await mark_dirty(db, partner_id, since)
            logger.error("Analytics rebuild failed", partner_id=partner_id, error=str(exc))
    return total


async def rebuild_today(db: AsyncSession) -> int:
    now = utcnow()
    return await rebuild(db, now - timedelta(hours=1) if now.hour == 0 else now)
