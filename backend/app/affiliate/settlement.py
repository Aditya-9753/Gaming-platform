"""Settlement period close / reopen (PRD §7, §8).

Close, in one transaction:
1. lock the period (OPEN -> CLOSING) so revenue for it is no longer accepted;
2. tiered deals: pick the tier from the partner's period NGR and adjust revshare;
3. settle: PENDING commission of the period plus HELD CPA whose hold ended
   moves pending -> available (only the not-yet-settled part, so a reopened
   period settles just the difference);
4. master partners earn their share of each direct subpartner's positive net;
5. carryover policy: write negative balances off (carryover off) or down to the cap;
6. write aff_partner_period_balances, create auto-withdrawals, notify;
7. CLOSED.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time as dtime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Set

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate import ledger
from app.affiliate import settings as aff_settings
from app.affiliate.commission import ensure_current_period, held_due, set_commission_amount, tier_rate
from app.affiliate.common import Actor, audit, notify
from app.affiliate.constants import (
    ZERO,
    Bucket,
    CommissionStatus,
    CommissionType,
    DealType,
    Direction,
    LedgerType,
    PartnerStatus,
    PeriodStatus,
)
from app.affiliate.partners import current_deal
from app.affiliate.util import money, utcnow
from app.core.exceptions import BadRequestException, ConflictException, ForbiddenException, NotFoundException
from app.models.affiliate import (
    AffCommission,
    AffPartner,
    AffPartnerPeriodBalance,
    AffSettlementPeriod,
    AffWalletTransaction,
    AffWallet,
)


async def get_period(db: AsyncSession, period_id: int, lock: bool = False) -> AffSettlementPeriod:
    query = select(AffSettlementPeriod).where(AffSettlementPeriod.id == period_id)
    if lock:
        query = query.with_for_update()
    period = (await db.execute(query)).scalar_one_or_none()
    if period is None:
        raise NotFoundException("Settlement period not found")
    return period


async def preview(db: AsyncSession, period_id: int) -> Dict[str, Any]:
    period = await get_period(db, period_id)
    rows = (
        await db.execute(
            select(AffCommission.partner_id, AffCommission.commission_type, AffCommission.status,
                   func.sum(AffCommission.commission_amount - AffCommission.settled_amount), func.count())
            .where(AffCommission.period_id == period_id, AffCommission.status != CommissionStatus.REVERSED)
            .group_by(AffCommission.partner_id, AffCommission.commission_type, AffCommission.status)
        )
    ).all()
    per_partner: Dict[int, Dict[str, Any]] = defaultdict(lambda: {"cpa": ZERO, "revshare": ZERO, "held": ZERO, "count": 0})
    for pid, ctype, status, amount, count in rows:
        bucket = per_partner[pid]
        amount = money(amount or 0)
        if CommissionStatus(status) == CommissionStatus.HELD:
            bucket["held"] += amount
        elif CommissionType(ctype) == CommissionType.CPA:
            bucket["cpa"] += amount
        else:
            bucket["revshare"] += amount
        bucket["count"] += int(count)
    total = sum((v["cpa"] + v["revshare"] for v in per_partner.values()), ZERO)
    return {
        "period": period,
        "partners": [{"partner_id": pid, **vals} for pid, vals in sorted(per_partner.items())],
        "total_to_settle": total,
        "held_total": sum((v["held"] for v in per_partner.values()), ZERO),
    }


async def _apply_tiers(db: AsyncSession, period: AffSettlementPeriod) -> None:
    revshare = (
        await db.execute(
            select(AffCommission).where(
                AffCommission.period_id == period.id, AffCommission.commission_type == CommissionType.REVSHARE,
                AffCommission.status != CommissionStatus.REVERSED,
            )
        )
    ).scalars().all()
    by_partner: Dict[int, List[AffCommission]] = defaultdict(list)
    for row in revshare:
        by_partner[row.partner_id].append(row)
    for partner_id, rows in by_partner.items():
        deal = await current_deal(db, partner_id, period.end_date)
        if deal is None or deal.deal_type != DealType.TIERED:
            continue
        period_ngr = sum((money(r.base_amount) for r in rows), ZERO)
        chosen = tier_rate(deal, period_ngr)
        for row in rows:
            if Decimal(row.rate) != chosen:
                row.rate = chosen
                await set_commission_amount(db, row, money(Decimal(row.base_amount) * chosen),
                                            reason=f"Tier rate {chosen * 100:.2f}% for period NGR {period_ngr:.2f}")
                # set_commission_amount may have moved it to the current open period; keep it in this one
                row.period_id = period.id


async def _settle(db: AsyncSession, period: AffSettlementPeriod, actor: Actor, now: datetime) -> Dict[int, Dict[str, Decimal]]:
    """Move unsettled amounts pending -> available. Returns per-partner settled totals by type."""
    due = list(
        (
            await db.execute(
                select(AffCommission).where(
                    AffCommission.period_id == period.id, AffCommission.status == CommissionStatus.PENDING,
                )
            )
        ).scalars().all()
    )
    due.extend(await held_due(db, now))
    totals: Dict[int, Dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    by_partner: Dict[int, List[AffCommission]] = defaultdict(list)
    for row in due:
        by_partner[row.partner_id].append(row)
    for partner_id, rows in by_partner.items():
        wallet = await ledger.lock_wallet(db, partner_id)
        net = ZERO
        for row in rows:
            delta = money(row.commission_amount) - money(row.settled_amount)
            row.status = CommissionStatus.APPROVED
            row.approved_at = now
            row.settled_amount = money(row.commission_amount)
            net += delta
            totals[partner_id][CommissionType(row.commission_type).value] += delta
        await ledger.move(
            db, wallet, entry_type=LedgerType.PERIOD_SETTLE, source=Bucket.PENDING, target=Bucket.AVAILABLE, amount=net,
            key=f"settle:{period.id}:{partner_id}:{int(now.timestamp())}", reference_type="settlement_period",
            reference_id=period.id, description=f"Period {period.start_date} - {period.end_date} settled",
            created_by=actor.user_id,
        )
    await db.flush()
    return totals


async def _subpartner_commissions(
    db: AsyncSession, period: AffSettlementPeriod, actor: Actor, totals: Dict[int, Dict[str, Decimal]], now: datetime
) -> None:
    if int(await aff_settings.get(db, "subpartner_depth")) < 1:
        return
    for sub_id, by_type in list(totals.items()):
        sub = await db.get(AffPartner, sub_id)
        if sub is None or sub.parent_partner_id is None:
            continue
        master = await db.get(AffPartner, sub.parent_partner_id)
        if master is None or master.status != PartnerStatus.ACTIVE or not master.subpartner_rate:
            continue
        net = sum((v for k, v in by_type.items() if k != CommissionType.SUBPARTNER.value), ZERO)
        if net <= ZERO:  # a negative subpartner period never costs the master
            continue
        amount = money(net * Decimal(master.subpartner_rate))
        if amount <= ZERO:
            continue
        commission = AffCommission(
            partner_id=master.id, customer_id=0, deposit_id=0, source_partner_id=sub.id, period_id=period.id,
            commission_type=CommissionType.SUBPARTNER, revenue_date=period.end_date, base_amount=net,
            rate=master.subpartner_rate, commission_amount=amount, status=CommissionStatus.APPROVED,
            approved_at=now, settled_amount=amount,
        )
        existing = (
            await db.execute(
                select(AffCommission).where(
                    AffCommission.partner_id == master.id, AffCommission.source_partner_id == sub.id,
                    AffCommission.commission_type == CommissionType.SUBPARTNER, AffCommission.revenue_date == period.end_date,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:  # reopened period: add the difference
            extra = amount
            existing.base_amount = money(existing.base_amount) + net
            existing.commission_amount = money(existing.commission_amount) + extra
            existing.settled_amount = money(existing.commission_amount)
            commission = existing
        else:
            db.add(commission)
            extra = amount
        await db.flush()
        wallet = await ledger.lock_wallet(db, master.id)
        await ledger.post(
            db, wallet, entry_type=LedgerType.SUBPARTNER_COMMISSION, bucket=Bucket.AVAILABLE, delta=extra,
            key=f"subcomm:{period.id}:{master.id}:{sub.id}:{int(now.timestamp())}", reference_type="commission",
            reference_id=commission.id, description=f"{Decimal(master.subpartner_rate) * 100:.2f}% of subpartner {sub.partner_code}",
            created_by=actor.user_id,
        )
        totals[master.id][CommissionType.SUBPARTNER.value] += extra


async def _carryover(db: AsyncSession, period: AffSettlementPeriod, actor: Actor, partner_id: int, now: datetime) -> Decimal:
    wallet = await ledger.lock_wallet(db, partner_id)
    available = money(wallet.available_balance)
    if available >= ZERO:
        return ZERO
    deal = await current_deal(db, partner_id, period.end_date)
    if deal is None:
        return ZERO
    if not deal.carryover:
        writeoff = -available
    elif deal.carryover_cap is not None and -available > money(deal.carryover_cap):
        writeoff = -available - money(deal.carryover_cap)
    else:
        return ZERO
    await ledger.post(
        db, wallet, entry_type=LedgerType.CARRYOVER_WRITEOFF, bucket=Bucket.AVAILABLE, delta=writeoff,
        key=f"writeoff:{period.id}:{partner_id}:{int(now.timestamp())}", reference_type="settlement_period",
        reference_id=period.id, description="Negative balance written off at period close", created_by=actor.user_id,
    )
    return writeoff


async def _period_sum(db: AsyncSession, wallet_id: int, types: List[LedgerType], start: datetime, end: datetime,
                      bucket: Bucket = Bucket.AVAILABLE) -> Decimal:
    rows = (
        await db.execute(
            select(AffWalletTransaction.direction, func.sum(AffWalletTransaction.amount))
            .where(AffWalletTransaction.wallet_id == wallet_id, AffWalletTransaction.type.in_(types),
                   AffWalletTransaction.bucket == bucket, AffWalletTransaction.created_at >= start,
                   AffWalletTransaction.created_at < end)
            .group_by(AffWalletTransaction.direction)
        )
    ).all()
    total = ZERO
    for direction, amount in rows:
        total += money(amount or 0) if Direction(direction) == Direction.CREDIT else -money(amount or 0)
    return total


async def close_period(db: AsyncSession, actor: Actor, period_id: int) -> Dict[str, Any]:
    from app.affiliate import withdrawals

    period = await get_period(db, period_id, lock=True)
    if period.status != PeriodStatus.OPEN:
        raise ConflictException(f"Period is {period.status.value}, only OPEN periods can be closed")
    today = utcnow().date()
    if period.end_date >= today and not actor.is_super:
        raise BadRequestException("This period has not ended yet (only the super admin can close it early)")
    period.status = PeriodStatus.CLOSING
    await db.flush()
    now = utcnow()

    # partners' available balance before anything moves (opening balance of the statement)
    wallets = {w.partner_id: w for w in (await db.execute(select(AffWallet))).scalars().all()}
    opening = {pid: money(w.available_balance) for pid, w in wallets.items()}

    await _apply_tiers(db, period)
    totals = await _settle(db, period, actor, now)
    await _subpartner_commissions(db, period, actor, totals, now)

    period_start = datetime.combine(period.start_date, dtime.min, tzinfo=timezone.utc)
    period_end = datetime.combine(period.end_date + timedelta(days=1), dtime.min, tzinfo=timezone.utc)
    touched: Set[int] = set(totals)
    touched.update(pid for pid, value in opening.items() if value < ZERO)
    statements = 0
    for partner_id in sorted(touched):
        writeoff = await _carryover(db, period, actor, partner_id, now)
        wallet = await ledger.lock_wallet(db, partner_id)
        by_type = totals.get(partner_id, {})
        adjustments = await _period_sum(db, wallet.id, [LedgerType.MANUAL_ADJUSTMENT], period_start, period_end)
        withdrawn = await _period_sum(db, wallet.id, [LedgerType.WITHDRAWAL_PAID], period_start, period_end, Bucket.RESERVED)
        values = dict(
            opening_balance=opening.get(partner_id, ZERO),
            cpa_total=money(by_type.get(CommissionType.CPA.value, ZERO)),
            revshare_total=money(by_type.get(CommissionType.REVSHARE.value, ZERO)),
            sub_commission_total=money(by_type.get(CommissionType.SUBPARTNER.value, ZERO)),
            adjustments_total=adjustments,
            withdrawals_total=-withdrawn,
            carryover_in=opening.get(partner_id, ZERO) if opening.get(partner_id, ZERO) < ZERO else ZERO,
            writeoff=writeoff,
            closing_balance=money(wallet.available_balance),
        )
        row = (
            await db.execute(
                select(AffPartnerPeriodBalance).where(AffPartnerPeriodBalance.partner_id == partner_id,
                                                      AffPartnerPeriodBalance.period_id == period.id)
            )
        ).scalar_one_or_none()
        if row is None:
            db.add(AffPartnerPeriodBalance(partner_id=partner_id, period_id=period.id, **values))
        else:  # reopened and closed again
            for key, value in values.items():
                setattr(row, key, value)
        statements += 1
        partner = await db.get(AffPartner, partner_id)
        settled = sum((v for v in by_type.values()), ZERO)
        if partner is not None and settled != ZERO:
            await notify(db, partner.user_id, "Period closed",
                         f"{period.start_date:%d %b} - {period.end_date:%d %b}: {settled:+.2f} $ moved to your available balance. "
                         f"Available now: {money(wallet.available_balance):.2f} $.")

    period.status = PeriodStatus.CLOSED
    period.closed_at = now
    period.closed_by = actor.user_id
    await db.flush()
    auto = await withdrawals.run_auto_withdrawals(db, period)
    await ensure_current_period(db)
    await audit(db, actor, "AFF_PERIOD_CLOSED", "aff_settlement_period", period.id,
                new={"start": str(period.start_date), "end": str(period.end_date), "statements": statements,
                     "auto_withdrawals": auto})
    await db.commit()
    from app.affiliate import analytics

    for pid in touched:
        await analytics.mark_dirty(db, pid, period_start)
    return {"period_id": period.id, "statements": statements, "auto_withdrawals": auto}


async def reopen_period(db: AsyncSession, actor: Actor, period_id: int, reason: str) -> AffSettlementPeriod:
    if not actor.is_super:
        raise ForbiddenException("Only the super admin can reopen a settlement period")
    period = await get_period(db, period_id, lock=True)
    if period.status != PeriodStatus.CLOSED:
        raise ConflictException("Only CLOSED periods can be reopened")
    later_closed = (
        await db.execute(
            select(AffSettlementPeriod.id).where(AffSettlementPeriod.start_date > period.end_date,
                                                  AffSettlementPeriod.status == PeriodStatus.CLOSED).limit(1)
        )
    ).first()
    if later_closed:
        raise ConflictException("A later period is already closed; reopen periods newest first")
    period.status = PeriodStatus.OPEN
    period.reopened_at = utcnow()
    await audit(db, actor, "AFF_PERIOD_REOPENED", "aff_settlement_period", period.id, reason=reason)
    await db.commit()
    return period


async def statements(db: AsyncSession, partner_id: int) -> List[Dict[str, Any]]:
    rows = (
        await db.execute(
            select(AffPartnerPeriodBalance, AffSettlementPeriod)
            .join(AffSettlementPeriod, AffSettlementPeriod.id == AffPartnerPeriodBalance.period_id)
            .where(AffPartnerPeriodBalance.partner_id == partner_id)
            .order_by(AffSettlementPeriod.start_date.desc())
        )
    ).all()
    return [{"balance": b, "period": p} for b, p in rows]


async def auto_close_due(db: AsyncSession, actor: Actor) -> List[int]:
    """Worker: close every OPEN period that ended before today (no-op when none)."""
    today = utcnow().date()
    due = (
        await db.execute(
            select(AffSettlementPeriod.id)
            .where(AffSettlementPeriod.status == PeriodStatus.OPEN, AffSettlementPeriod.end_date < today)
            .order_by(AffSettlementPeriod.start_date)
        )
    ).scalars().all()
    closed = []
    for period_id in due:
        await close_period(db, actor, period_id)
        closed.append(period_id)
    return closed
