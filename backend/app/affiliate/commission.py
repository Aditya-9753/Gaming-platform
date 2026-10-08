"""Commission engine: revshare per player per day, CPA per qualified FTD (PRD §7).

One commission row per (partner, customer, date, type). When revenue for a day
changes, the commission is recomputed and only the *difference* is posted to the
ledger as COMMISSION_ADJUSTMENT; ledger entries are never edited.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate import ledger
from app.affiliate import settings as aff_settings
from app.affiliate.common import Actor, SYSTEM, audit, notify, risk_event
from app.affiliate.constants import (
    ZERO,
    Bucket,
    CommissionStatus,
    CommissionType,
    DealType,
    LedgerType,
    PeriodStatus,
    PeriodType,
    RegistrationStatus,
    RiskSeverity,
)
from app.affiliate.partners import current_deal
from app.affiliate.util import aware, money, month_bounds, utcnow, week_start
from app.models.affiliate import (
    AffCommission,
    AffCustomer,
    AffDeposit,
    AffPartner,
    AffPartnerDeal,
    AffPlayerRevenueDaily,
    AffRegistration,
    AffSettlementPeriod,
)

# ---------------------------------------------------------------------------
# Settlement periods
# ---------------------------------------------------------------------------


async def containing_period(db: AsyncSession, day: date) -> Optional[AffSettlementPeriod]:
    return (
        await db.execute(
            select(AffSettlementPeriod)
            .where(AffSettlementPeriod.start_date <= day, AffSettlementPeriod.end_date >= day)
            .order_by(AffSettlementPeriod.start_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _create_period(db: AsyncSession, day: date) -> AffSettlementPeriod:
    kind = PeriodType(await aff_settings.get(db, "settlement_period_type"))
    if kind == PeriodType.WEEKLY:
        start, end = week_start(day), week_start(day) + timedelta(days=6)
    else:
        start, end = month_bounds(day)
    latest_end = (await db.execute(select(func.max(AffSettlementPeriod.end_date)))).scalar_one_or_none()
    if latest_end is not None and latest_end >= start:
        start = latest_end + timedelta(days=1)
        if start > end:  # the type changed and the old period already covers this one
            end = start + timedelta(days=6 if kind == PeriodType.WEEKLY else 27)
    period = AffSettlementPeriod(period_type=kind, start_date=start, end_date=end, status=PeriodStatus.OPEN)
    db.add(period)
    await db.flush()
    return period


async def open_period_for(db: AsyncSession, day: date) -> AffSettlementPeriod:
    """The OPEN period commission dated ``day`` belongs to (late data rolls into the next open period)."""
    period = await containing_period(db, day)
    if period is None:
        period = await _create_period(db, day)
    if period.status == PeriodStatus.OPEN:
        return period
    nxt = (
        await db.execute(
            select(AffSettlementPeriod)
            .where(AffSettlementPeriod.start_date > period.end_date, AffSettlementPeriod.status == PeriodStatus.OPEN)
            .order_by(AffSettlementPeriod.start_date)
            .limit(1)
        )
    ).scalar_one_or_none()
    if nxt is not None:
        return nxt
    latest_end = (await db.execute(select(func.max(AffSettlementPeriod.end_date)))).scalar_one()
    return await _create_period(db, latest_end + timedelta(days=1))


async def ensure_current_period(db: AsyncSession) -> AffSettlementPeriod:
    return await open_period_for(db, utcnow().date())


# ---------------------------------------------------------------------------
# Revshare
# ---------------------------------------------------------------------------


def revshare_rate(deal: AffPartnerDeal) -> Decimal:
    if deal.deal_type in (DealType.REVSHARE, DealType.HYBRID, DealType.TIERED):
        return Decimal(deal.revshare_rate or 0)
    return ZERO


def tier_rate(deal: AffPartnerDeal, period_ngr: Decimal) -> Decimal:
    chosen = Decimal(deal.revshare_rate or 0)
    for tier in deal.tier_table or []:
        if period_ngr >= Decimal(str(tier["min_ngr"])):
            chosen = Decimal(str(tier["rate"]))
    return chosen


async def _registration(db: AsyncSession, customer_id: int) -> Optional[AffRegistration]:
    return (await db.execute(select(AffRegistration).where(AffRegistration.customer_id == customer_id))).scalar_one_or_none()


async def set_commission_amount(
    db: AsyncSession, commission: AffCommission, new_amount: Decimal, *, reason: str, actor: Actor = SYSTEM
) -> Decimal:
    """Change a commission's amount and post the difference to the right bucket. Returns the delta."""
    new_amount = money(new_amount)
    delta = new_amount - money(commission.commission_amount)
    if delta == ZERO:
        return ZERO
    wallet = await ledger.lock_wallet(db, commission.partner_id)
    key = f"comm-adj:{commission.id}:{uuid.uuid4().hex}"
    # A settled commission's change goes to pending again and the commission re-enters settlement
    await ledger.post(
        db, wallet, entry_type=LedgerType.COMMISSION_ADJUSTMENT, bucket=Bucket.PENDING, delta=delta, key=key,
        reference_type="commission", reference_id=commission.id, description=reason, created_by=actor.user_id,
    )
    commission.commission_amount = new_amount
    if commission.status == CommissionStatus.APPROVED:
        commission.status = CommissionStatus.PENDING
        period = await open_period_for(db, utcnow().date())
        commission.period_id = period.id
    await db.flush()
    return delta


async def process_revenue_rows(db: AsyncSession, rows: Iterable[AffPlayerRevenueDaily]) -> int:
    """Recompute revshare for changed revenue rows. Flushes; caller commits."""
    count = 0
    for row in rows:
        reg = await _registration(db, row.customer_id)
        row.needs_commission = False
        if reg is None or reg.status != RegistrationStatus.ACTIVE:
            continue
        deal = await current_deal(db, reg.partner_id, row.revenue_date)
        if deal is None:
            continue
        rate = revshare_rate(deal)
        amount = money(Decimal(row.ngr) * rate)
        existing = (
            await db.execute(
                select(AffCommission).where(
                    AffCommission.partner_id == reg.partner_id,
                    AffCommission.customer_id == row.customer_id,
                    AffCommission.revenue_date == row.revenue_date,
                    AffCommission.commission_type == CommissionType.REVSHARE,
                    AffCommission.deposit_id == 0,
                    AffCommission.source_partner_id == 0,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            if rate == ZERO:
                continue
            period = await open_period_for(db, row.revenue_date)
            commission = AffCommission(
                partner_id=reg.partner_id, customer_id=row.customer_id, deal_id=deal.id, period_id=period.id,
                commission_type=CommissionType.REVSHARE, revenue_date=row.revenue_date, base_amount=money(row.ngr),
                rate=rate, commission_amount=amount, status=CommissionStatus.PENDING,
            )
            db.add(commission)
            await db.flush()
            wallet = await ledger.lock_wallet(db, reg.partner_id)
            await ledger.post(
                db, wallet, entry_type=LedgerType.COMMISSION_REVSHARE, bucket=Bucket.PENDING, delta=amount,
                key=f"comm:{commission.id}:initial", reference_type="commission", reference_id=commission.id,
                description=f"Revshare {row.revenue_date} customer #{row.customer_id}",
            )
        else:
            existing.base_amount = money(row.ngr)
            existing.rate = rate
            existing.deal_id = deal.id
            await set_commission_amount(db, existing, amount, reason=f"Revenue update {row.revenue_date}")
        count += 1
    await db.flush()
    return count


async def process_dirty_revenue(db: AsyncSession, limit: int = 5000) -> int:
    rows = (
        await db.execute(
            select(AffPlayerRevenueDaily).where(AffPlayerRevenueDaily.needs_commission.is_(True)).limit(limit)
        )
    ).scalars().all()
    done = await process_revenue_rows(db, rows)
    await db.commit()
    return done


# ---------------------------------------------------------------------------
# CPA
# ---------------------------------------------------------------------------


async def on_first_deposit(db: AsyncSession, deposit: AffDeposit) -> Optional[AffCommission]:
    """CPA for a qualified FTD: held for ``hold_days`` before it can settle."""
    if not deposit.is_first_deposit or deposit.partner_id is None or deposit.is_fraud:
        return None
    reg = await _registration(db, deposit.customer_id)
    if reg is None or reg.status != RegistrationStatus.ACTIVE:
        return None
    completed = aware(deposit.completed_at) or utcnow()
    deal = await current_deal(db, deposit.partner_id, completed.date())
    if deal is None or deal.deal_type not in (DealType.CPA, DealType.HYBRID):
        return None
    customer = await db.get(AffCustomer, deposit.customer_id)
    country = (customer.country if customer else None) or reg.country
    if money(deposit.amount_usd) < money(deal.min_ftd_amount):
        return None
    if deal.cpa_geo_list and (country or "") not in deal.cpa_geo_list:
        return None
    deposit.qualified_for_cpa = True
    period = await open_period_for(db, completed.date())
    held = deal.hold_days > 0
    commission = AffCommission(
        partner_id=deposit.partner_id, customer_id=deposit.customer_id, deposit_id=deposit.id, deal_id=deal.id,
        period_id=period.id, commission_type=CommissionType.CPA, revenue_date=completed.date(),
        base_amount=money(deposit.amount_usd), rate=Decimal("0"), commission_amount=money(deal.cpa_amount),
        status=CommissionStatus.HELD if held else CommissionStatus.PENDING,
        hold_until=completed + timedelta(days=deal.hold_days) if held else None,
    )
    db.add(commission)
    await db.flush()
    wallet = await ledger.lock_wallet(db, deposit.partner_id)
    await ledger.post(
        db, wallet, entry_type=LedgerType.COMMISSION_CPA, bucket=Bucket.PENDING, delta=commission.commission_amount,
        key=f"comm:{commission.id}:initial", reference_type="commission", reference_id=commission.id,
        description=f"CPA for first deposit of customer #{deposit.customer_id}",
    )
    partner = await db.get(AffPartner, deposit.partner_id)
    if partner is not None:
        await notify(db, partner.user_id, "New qualified first deposit",
                     f"CPA {money(deal.cpa_amount):.2f} $ is on hold until {commission.hold_until:%d %b %Y}." if held
                     else f"CPA {money(deal.cpa_amount):.2f} $ added to your pending balance.")
    return commission


async def reverse_cpa(db: AsyncSession, deposit: AffDeposit, reason: str, actor: Actor = SYSTEM) -> Optional[AffCommission]:
    """Chargeback / fraud: take the CPA back (from pending if unsettled, else from available)."""
    commission = (
        await db.execute(
            select(AffCommission).where(
                AffCommission.deposit_id == deposit.id, AffCommission.commission_type == CommissionType.CPA
            )
        )
    ).scalar_one_or_none()
    if commission is None or commission.status == CommissionStatus.REVERSED:
        return None
    wallet = await ledger.lock_wallet(db, commission.partner_id)
    unsettled = money(commission.commission_amount) - money(commission.settled_amount)
    if unsettled != ZERO:
        await ledger.post(
            db, wallet, entry_type=LedgerType.COMMISSION_ADJUSTMENT, bucket=Bucket.PENDING, delta=-unsettled,
            key=f"comm:{commission.id}:reverse-pending", reference_type="commission", reference_id=commission.id,
            description=f"CPA reversed: {reason}", created_by=actor.user_id,
        )
    if money(commission.settled_amount) != ZERO:
        await ledger.post(
            db, wallet, entry_type=LedgerType.COMMISSION_ADJUSTMENT, bucket=Bucket.AVAILABLE,
            delta=-money(commission.settled_amount), key=f"comm:{commission.id}:reverse-available",
            reference_type="commission", reference_id=commission.id, description=f"CPA reversed: {reason}",
            created_by=actor.user_id,
        )
    commission.status = CommissionStatus.REVERSED
    deposit.qualified_for_cpa = False
    await risk_event(
        db, "CPA_REVERSED", RiskSeverity.MEDIUM, f"CPA reversed for deposit #{deposit.id}: {reason}",
        partner_id=commission.partner_id, customer_id=deposit.customer_id, score=40,
        meta={"deposit_id": deposit.id, "amount": str(commission.commission_amount)},
        dedupe_key=f"cpa-reversed:{commission.id}",
    )
    await audit(db, actor, "AFF_CPA_REVERSED", "aff_commission", commission.id, reason=reason)
    partner = await db.get(AffPartner, commission.partner_id)
    if partner is not None:
        await notify(db, partner.user_id, "CPA reversed", f"A CPA of {money(commission.commission_amount):.2f} $ was reversed: {reason}", "WARNING")
    return commission


async def commissions_for_period(db: AsyncSession, period_id: int, partner_ids: Optional[List[int]] = None) -> List[AffCommission]:
    query = select(AffCommission).where(AffCommission.period_id == period_id)
    if partner_ids:
        query = query.where(AffCommission.partner_id.in_(partner_ids))
    return list((await db.execute(query)).scalars().all())


async def held_due(db: AsyncSession, now) -> List[AffCommission]:
    return list(
        (
            await db.execute(
                select(AffCommission).where(
                    and_(AffCommission.status == CommissionStatus.HELD, AffCommission.hold_until <= now)
                )
            )
        ).scalars().all()
    )
