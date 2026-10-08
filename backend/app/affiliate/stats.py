"""Dashboard KPIs, chart series and statistics, read from the analytics tables (PRD §3, §4).

KPI formulas (reconcile with the reference numbers):
  transitions          valid clicks (bots / fraud removed)
  ratio_registrations  transitions / registrations   (clicks needed per signup)
  ratio_deposits       deposit amount / registrations ($ deposited per signup)
  cost_transition      income / transitions          (EPC)
  avg_player_income    revshare deal: (income / rate) / FTD; otherwise NGR / FTD
Division by zero gives None (shown as "—").
"""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import date, datetime, time as dtime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate.constants import ZERO, CommissionStatus, CommissionType, DealType, DepositStatus, RegistrationStatus
from app.affiliate.partners import current_deal
from app.affiliate.util import money, money_out
from app.core.exceptions import BadRequestException
from app.models.affiliate import (
    AffAnalyticsHourly,
    AffCommission,
    AffDeposit,
    AffPartner,
    AffRegistration,
    AffSource,
    AffTrackingClick,
    AffTrackingLink,
)

# Constants are inlined as SQL text: GROUP BY must repeat the SELECT expression exactly, and with
# bind parameters ($1 in SELECT, $4 in GROUP BY under asyncpg) PostgreSQL treats them as different.
ZERO_SQL = literal_column("0")
EMPTY_SQL = literal_column("''")

PRESETS = ("today", "yesterday", "7d", "30d", "this_month", "last_month", "all", "custom")
_MONEY = ("deposit_amount", "ngr", "income", "sub_commission")
_COUNTS = ("clicks", "unique_clicks", "registrations", "first_deposits", "deposit_count")
CACHE_SECONDS = 60


def tz_of(name: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def period_range(preset: str, tz_name: str, date_from: Optional[date] = None, date_to: Optional[date] = None
                 ) -> Tuple[Optional[datetime], Optional[datetime], Optional[date], Optional[date]]:
    """(start_utc, end_utc, first_local_day, last_local_day); all None for "all"."""
    tz = tz_of(tz_name)
    today = datetime.now(tz).date()
    if preset == "today":
        first, last = today, today
    elif preset == "yesterday":
        first = last = today - timedelta(days=1)
    elif preset == "7d":
        first, last = today - timedelta(days=6), today
    elif preset == "30d":
        first, last = today - timedelta(days=29), today
    elif preset == "this_month":
        first, last = today.replace(day=1), today
    elif preset == "last_month":
        last = today.replace(day=1) - timedelta(days=1)
        first = last.replace(day=1)
    elif preset == "custom":
        if not date_from or not date_to or date_to < date_from:
            raise BadRequestException("Choose a valid date range")
        if (date_to - date_from).days > 731:
            raise BadRequestException("Choose at most two years")
        first, last = date_from, date_to
    elif preset == "all":
        return None, None, None, None
    else:
        raise BadRequestException(f"period must be one of {', '.join(PRESETS)}")
    start = datetime.combine(first, dtime.min, tzinfo=tz).astimezone(timezone.utc)
    end = datetime.combine(last + timedelta(days=1), dtime.min, tzinfo=tz).astimezone(timezone.utc)
    return start, end, first, last


def _filters(partner_ids: Sequence[int], start: Optional[datetime], end: Optional[datetime], source_ids: Sequence[int] = (),
             link_ids: Sequence[int] = (), countries: Sequence[str] = ()) -> List[Any]:
    clauses = [AffAnalyticsHourly.partner_id.in_(list(partner_ids))]
    if start is not None:
        clauses.append(AffAnalyticsHourly.date_hour >= start)
    if end is not None:
        clauses.append(AffAnalyticsHourly.date_hour < end)
    if source_ids:
        clauses.append(AffAnalyticsHourly.source_id.in_(list(source_ids)))
    if link_ids:
        clauses.append(AffAnalyticsHourly.tracking_link_id.in_(list(link_ids)))
    if countries:
        clauses.append(AffAnalyticsHourly.country.in_([c.upper() for c in countries]))
    return clauses


def _sums() -> List[Any]:
    return [func.coalesce(func.sum(getattr(AffAnalyticsHourly, m)), 0).label(m) for m in _COUNTS + _MONEY]


def _row_dict(row: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for m in _COUNTS:
        out[m] = int(getattr(row, m) or 0)
    for m in _MONEY:
        out[m] = money(getattr(row, m) or 0)
    return out


def _div(a: Decimal, b: Decimal, places: str = "0.01") -> Optional[str]:
    if not b:
        return None
    return str((Decimal(a) / Decimal(b)).quantize(Decimal(places), rounding=ROUND_HALF_UP))


def kpis(totals: Dict[str, Any], deal_type: Optional[DealType], revshare_rate: Decimal) -> Dict[str, Any]:
    clicks, regs, ftd = totals["clicks"], totals["registrations"], totals["first_deposits"]
    income, ngr = totals["income"], totals["ngr"]
    if deal_type == DealType.REVSHARE and revshare_rate:
        avg_player = _div(income / revshare_rate, Decimal(ftd)) if ftd else None
    else:
        avg_player = _div(ngr, Decimal(ftd))
    return {
        "transitions": clicks,
        "registrations": regs,
        "first_deposits": ftd,
        "deposit_count": totals["deposit_count"],
        "ratio_registrations": _div(Decimal(clicks), Decimal(regs)),
        "ratio_deposits": _div(totals["deposit_amount"], Decimal(regs)),
        "amount_deposit": money_out(totals["deposit_amount"]),
        "cost_transition": _div(income, Decimal(clicks)),
        "avg_player_income": avg_player,
        "income": money_out(income),
        "sub_commission": money_out(totals["sub_commission"]),
        "ngr": money_out(ngr),
        "unique_clicks": totals["unique_clicks"],
    }


async def _cached(key: str, producer: Any) -> Any:
    from app.core.redis import get_redis_client

    try:
        redis = get_redis_client()
        hit = await redis.get(key)
        if hit:
            return json.loads(hit)
    except Exception:
        redis = None
    value = await producer()
    if redis is not None:
        try:
            await redis.set(key, json.dumps(value, default=str), ex=CACHE_SECONDS)
        except Exception:
            pass
    return value


async def summary(db: AsyncSession, partner: AffPartner, preset: str, date_from: Optional[date] = None,
                  date_to: Optional[date] = None, source_ids: Sequence[int] = (), link_ids: Sequence[int] = (),
                  countries: Sequence[str] = (), use_cache: bool = True) -> Dict[str, Any]:
    async def produce() -> Dict[str, Any]:
        start, end, first, last = period_range(preset, partner.timezone, date_from, date_to)
        row = (await db.execute(select(*_sums()).where(*_filters([partner.id], start, end, source_ids, link_ids, countries)))).one()
        totals = _row_dict(row)
        deal = await current_deal(db, partner.id)
        return {
            "period": preset, "from": first.isoformat() if first else None, "to": last.isoformat() if last else None,
            "timezone": partner.timezone,
            "deal": {"type": deal.deal_type.value if deal else None, "revshare_rate": str(deal.revshare_rate) if deal else None},
            **kpis(totals, deal.deal_type if deal else None, Decimal(deal.revshare_rate) if deal else ZERO),
        }

    key = f"aff:dash:{partner.id}:{preset}:{date_from}:{date_to}:{sorted(source_ids)}:{sorted(link_ids)}:{sorted(countries)}"
    return await _cached(key, produce) if use_cache else await produce()


async def timeseries(db: AsyncSession, partner_ids: Sequence[int], tz_name: str, preset: str, date_from: Optional[date] = None,
                     date_to: Optional[date] = None, source_ids: Sequence[int] = (), link_ids: Sequence[int] = (),
                     countries: Sequence[str] = ()) -> List[Dict[str, Any]]:
    start, end, first, last = period_range(preset, tz_name, date_from, date_to)
    tz = tz_of(tz_name)
    rows = (
        await db.execute(
            select(AffAnalyticsHourly.date_hour, *_sums())
            .where(*_filters(partner_ids, start, end, source_ids, link_ids, countries))
            .group_by(AffAnalyticsHourly.date_hour)
        )
    ).all()
    days: Dict[date, Dict[str, Any]] = defaultdict(lambda: {**{m: 0 for m in _COUNTS}, **{m: ZERO for m in _MONEY}})
    for row in rows:
        hour = row.date_hour if row.date_hour.tzinfo else row.date_hour.replace(tzinfo=timezone.utc)
        bucket = days[hour.astimezone(tz).date()]
        for m in _COUNTS:
            bucket[m] += int(getattr(row, m) or 0)
        for m in _MONEY:
            bucket[m] += money(getattr(row, m) or 0)
    if first is None:
        if not days:
            return []
        first, last = min(days), max(max(days), datetime.now(tz).date())
    if (last - first).days > 731:
        first = last - timedelta(days=731)
    series = []
    day = first
    while day <= last:
        b = days.get(day) or {**{m: 0 for m in _COUNTS}, **{m: ZERO for m in _MONEY}}
        series.append({
            "date": day.isoformat(), "referrals": b["clicks"], "registrations": b["registrations"],
            "income": money_out(b["income"]), "first_deposits": b["first_deposits"], "deposit_amount": money_out(b["deposit_amount"]),
        })
        day += timedelta(days=1)
    return series


async def filter_options(db: AsyncSession, partner_id: int) -> Dict[str, Any]:
    sources = (await db.execute(select(AffSource.id, AffSource.name).where(AffSource.partner_id == partner_id).order_by(AffSource.id))).all()
    links = (await db.execute(select(AffTrackingLink.id, AffTrackingLink.name, AffTrackingLink.link_code, AffTrackingLink.source_id)
                              .where(AffTrackingLink.partner_id == partner_id).order_by(AffTrackingLink.id))).all()
    countries = (await db.execute(select(AffAnalyticsHourly.country).where(
        AffAnalyticsHourly.partner_id == partner_id, AffAnalyticsHourly.country != "").distinct())).scalars().all()
    return {
        "sources": [{"id": s.id, "name": s.name} for s in sources],
        "links": [{"id": l.id, "name": l.name, "code": l.link_code, "source_id": l.source_id} for l in links],
        "countries": sorted(countries),
    }


GROUPS = ("day", "source", "link", "country", "campaign", "sub1", "partner")


async def grouped(db: AsyncSession, partner_ids: Sequence[int], tz_name: str, preset: str, group_by: str,
                  date_from: Optional[date] = None, date_to: Optional[date] = None, source_ids: Sequence[int] = (),
                  link_ids: Sequence[int] = (), countries: Sequence[str] = ()) -> List[Dict[str, Any]]:
    if group_by not in GROUPS:
        raise BadRequestException(f"group_by must be one of {', '.join(GROUPS)}")
    if group_by == "sub1":
        return await _grouped_sub1(db, partner_ids, tz_name, preset, date_from, date_to)
    if group_by == "day":
        series = await timeseries(db, partner_ids, tz_name, preset, date_from, date_to, source_ids, link_ids, countries)
        return [{"key": s["date"], "label": s["date"], "clicks": s["referrals"], "registrations": s["registrations"],
                 "first_deposits": s["first_deposits"], "deposit_amount": s["deposit_amount"], "income": s["income"]} for s in series]
    start, end, _f, _l = period_range(preset, tz_name, date_from, date_to)
    column = {"source": AffAnalyticsHourly.source_id, "link": AffAnalyticsHourly.tracking_link_id,
              "country": AffAnalyticsHourly.country, "campaign": AffAnalyticsHourly.campaign_id,
              "partner": AffAnalyticsHourly.partner_id}[group_by]
    rows = (await db.execute(select(column.label("key"), *_sums()).where(
        *_filters(partner_ids, start, end, source_ids, link_ids, countries)).group_by(column))).all()
    labels: Dict[Any, str] = {}
    keys = [r.key for r in rows]
    if group_by == "source" and keys:
        labels = {i: n for i, n in (await db.execute(select(AffSource.id, AffSource.name).where(AffSource.id.in_(keys)))).all()}
    elif group_by == "link" and keys:
        labels = {i: f"{n} ({c})" for i, n, c in (await db.execute(select(AffTrackingLink.id, AffTrackingLink.name, AffTrackingLink.link_code).where(AffTrackingLink.id.in_(keys)))).all()}
    elif group_by == "partner" and keys:
        labels = {i: c for i, c in (await db.execute(select(AffPartner.id, AffPartner.partner_code).where(AffPartner.id.in_(keys)))).all()}
    out = []
    for row in rows:
        totals = _row_dict(row)
        out.append({
            "key": row.key, "label": labels.get(row.key) or (row.key if row.key not in (0, "") else "—"),
            "clicks": totals["clicks"], "registrations": totals["registrations"], "first_deposits": totals["first_deposits"],
            "deposit_count": totals["deposit_count"], "deposit_amount": money_out(totals["deposit_amount"]),
            "ngr": money_out(totals["ngr"]), "income": money_out(totals["income"]),
            "ratio_registrations": _div(Decimal(totals["clicks"]), Decimal(totals["registrations"])),
            "cost_transition": _div(totals["income"], Decimal(totals["clicks"])),
        })
    out.sort(key=lambda r: (-r["clicks"], str(r["label"])))
    return out


async def _grouped_sub1(db: AsyncSession, partner_ids: Sequence[int], tz_name: str, preset: str,
                        date_from: Optional[date], date_to: Optional[date]) -> List[Dict[str, Any]]:
    """sub1 is not an analytics dimension, so it is grouped from the raw tables."""
    start, end, _f, _l = period_range(preset, tz_name, date_from, date_to)
    pids = list(partner_ids)
    agg: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"clicks": 0, "registrations": 0, "first_deposits": 0, "deposit_amount": ZERO, "income": ZERO})

    def window(column: Any) -> List[Any]:
        clauses = []
        if start is not None:
            clauses.append(column >= start)
        if end is not None:
            clauses.append(column < end)
        return clauses

    for key, total in (await db.execute(
        select(func.coalesce(AffTrackingClick.sub1, EMPTY_SQL), func.count()).where(
            AffTrackingClick.partner_id.in_(pids), AffTrackingClick.is_bot.is_(False), AffTrackingClick.is_fraud.is_(False),
            *window(AffTrackingClick.clicked_at)).group_by(func.coalesce(AffTrackingClick.sub1, EMPTY_SQL)))).all():
        agg[key]["clicks"] += int(total)
    for key, total in (await db.execute(
        select(func.coalesce(AffRegistration.sub1, EMPTY_SQL), func.count()).where(
            AffRegistration.partner_id.in_(pids), AffRegistration.status == RegistrationStatus.ACTIVE,
            *window(AffRegistration.registered_at)).group_by(func.coalesce(AffRegistration.sub1, EMPTY_SQL)))).all():
        agg[key]["registrations"] += int(total)
    for key, ftd, amount in (await db.execute(
        select(func.coalesce(AffRegistration.sub1, EMPTY_SQL), func.sum(case((AffDeposit.is_first_deposit.is_(True), 1), else_=0)), func.sum(AffDeposit.amount_usd))
        .join(AffRegistration, AffRegistration.customer_id == AffDeposit.customer_id)
        .where(AffRegistration.partner_id.in_(pids), AffDeposit.status == DepositStatus.COMPLETED, *window(AffDeposit.completed_at))
        .group_by(func.coalesce(AffRegistration.sub1, EMPTY_SQL)))).all():
        agg[key]["first_deposits"] += int(ftd or 0)
        agg[key]["deposit_amount"] += money(amount or 0)
    date_clauses = []
    if start is not None:
        date_clauses.append(AffCommission.revenue_date >= start.date())
    if end is not None:
        date_clauses.append(AffCommission.revenue_date < end.date())
    for key, amount in (await db.execute(
        select(func.coalesce(AffRegistration.sub1, EMPTY_SQL), func.sum(AffCommission.commission_amount))
        .join(AffRegistration, AffRegistration.customer_id == AffCommission.customer_id)
        .where(AffCommission.partner_id.in_(pids), AffCommission.status != CommissionStatus.REVERSED,
               AffCommission.commission_type.in_([CommissionType.CPA, CommissionType.REVSHARE]), *date_clauses)
        .group_by(func.coalesce(AffRegistration.sub1, EMPTY_SQL)))).all():
        agg[key]["income"] += money(amount or 0)
    out = [{"key": k, "label": k or "—", "clicks": v["clicks"], "registrations": v["registrations"], "first_deposits": v["first_deposits"],
            "deposit_amount": money_out(v["deposit_amount"]), "income": money_out(v["income"]),
            "ratio_registrations": _div(Decimal(v["clicks"]), Decimal(v["registrations"])),
            "cost_transition": _div(v["income"], Decimal(v["clicks"]))} for k, v in agg.items()]
    out.sort(key=lambda r: -r["clicks"])
    return out


async def subpartner_stats(db: AsyncSession, master: AffPartner, preset: str, date_from: Optional[date] = None,
                           date_to: Optional[date] = None) -> List[Dict[str, Any]]:
    """Direct children only, aggregates only (never their customers)."""
    from app.models.user import User

    children = (await db.execute(select(AffPartner, User.email).join(User, User.id == AffPartner.user_id)
                                 .where(AffPartner.parent_partner_id == master.id).order_by(AffPartner.id))).all()
    if not children:
        return []
    start, end, _f, _l = period_range(preset, master.timezone, date_from, date_to)
    ids = [c.id for c, _e in children]
    rows = {r.partner_id: _row_dict(r) for r in (await db.execute(
        select(AffAnalyticsHourly.partner_id, *_sums()).where(*_filters(ids, start, end)).group_by(AffAnalyticsHourly.partner_id))).all()}
    clauses = [AffCommission.partner_id == master.id, AffCommission.commission_type == CommissionType.SUBPARTNER]
    if start is not None:
        clauses.append(AffCommission.revenue_date >= start.date())
    if end is not None:
        clauses.append(AffCommission.revenue_date < end.date())
    earned = {sid: money(total or 0) for sid, total in (await db.execute(
        select(AffCommission.source_partner_id, func.sum(AffCommission.commission_amount)).where(*clauses)
        .group_by(AffCommission.source_partner_id))).all()}
    out = []
    for child, email in children:
        t = rows.get(child.id) or {**{m: 0 for m in _COUNTS}, **{m: ZERO for m in _MONEY}}
        name, _, domain = (email or "").partition("@")
        out.append({
            "partner_code": child.partner_code, "email_masked": f"{name[:2]}***@{domain}" if domain else "—",
            "status": child.status.value, "joined_at": child.created_at.isoformat() if child.created_at else None,
            "clicks": t["clicks"], "registrations": t["registrations"], "first_deposits": t["first_deposits"],
            "income": money_out(t["income"]), "your_commission": money_out(earned.get(child.id, ZERO)),
        })
    return out


def to_csv(rows: List[Dict[str, Any]]) -> str:
    out = io.StringIO()
    if not rows:
        return ""
    writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()
