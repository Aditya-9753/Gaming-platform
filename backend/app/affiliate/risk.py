"""Risk actions: payout freezes, fraud marking (reverses CPA), event review."""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate import commission
from app.affiliate.common import Actor, audit, notify
from app.affiliate.constants import RiskStatus
from app.affiliate.partners import get_partner
from app.affiliate.tracking import find_click
from app.affiliate.util import utcnow
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.affiliate import AffDeposit, AffRegistration, AffRiskEvent, AffTrackingClick


async def set_payout_freeze(db: AsyncSession, actor: Actor, partner_id: int, frozen: bool, reason: str) -> None:
    if not reason.strip():
        raise BadRequestException("Give a reason")
    partner = await get_partner(db, partner_id)
    old = partner.payout_frozen
    partner.payout_frozen = frozen
    await audit(db, actor, "AFF_PAYOUT_FREEZE" if frozen else "AFF_PAYOUT_UNFREEZE", "aff_partner", partner_id,
                old={"payout_frozen": old}, new={"payout_frozen": frozen}, reason=reason)
    await notify(db, partner.user_id, "Payouts frozen" if frozen else "Payouts resumed",
                 f"{'Payouts on your account are on hold' if frozen else 'Payouts on your account are active again'}: {reason}", "WARNING")


async def mark_deposit_fraud(db: AsyncSession, actor: Actor, deposit_id: int, reason: str) -> AffDeposit:
    deposit = await db.get(AffDeposit, deposit_id)
    if deposit is None:
        raise NotFoundException("Deposit not found")
    deposit.is_fraud = True
    await commission.reverse_cpa(db, deposit, f"fraud: {reason}", actor)
    await audit(db, actor, "AFF_DEPOSIT_FRAUD", "aff_deposit", deposit_id, reason=reason)
    return deposit


async def mark_registration_fraud(db: AsyncSession, actor: Actor, registration_id: int, reason: str) -> AffRegistration:
    from app.affiliate.constants import RegistrationStatus

    reg = await db.get(AffRegistration, registration_id)
    if reg is None:
        raise NotFoundException("Registration not found")
    reg.status = RegistrationStatus.FRAUD
    for deposit in (await db.execute(select(AffDeposit).where(AffDeposit.customer_id == reg.customer_id,
                                                              AffDeposit.qualified_for_cpa.is_(True)))).scalars():
        await commission.reverse_cpa(db, deposit, f"fraud registration: {reason}", actor)
    await audit(db, actor, "AFF_REGISTRATION_FRAUD", "aff_registration", registration_id, reason=reason)
    return reg


async def mark_click_fraud(db: AsyncSession, actor: Actor, click_id: str, reason: str) -> AffTrackingClick:
    click = await find_click(db, click_id)
    if click is None:
        raise NotFoundException("Click not found")
    click.is_fraud = True
    await audit(db, actor, "AFF_CLICK_FRAUD", "aff_tracking_click", click_id, reason=reason)
    return click


async def mark_ip_clicks_fraud(db: AsyncSession, actor: Actor, partner_id: int, ip_hash: str, hours: int, reason: str) -> int:
    since = utcnow() - timedelta(hours=max(1, min(hours, 24 * 31)))
    result = await db.execute(
        update(AffTrackingClick)
        .where(AffTrackingClick.partner_id == partner_id, AffTrackingClick.ip_hash == ip_hash, AffTrackingClick.clicked_at >= since)
        .values(is_fraud=True)
    )
    await audit(db, actor, "AFF_CLICKS_FRAUD", "aff_partner", partner_id, ip_hash=ip_hash, hours=hours, reason=reason, rows=result.rowcount)
    return int(result.rowcount or 0)


async def review_event(db: AsyncSession, actor: Actor, event_id: int, status: RiskStatus, note: Optional[str]) -> AffRiskEvent:
    row = await db.get(AffRiskEvent, event_id)
    if row is None:
        raise NotFoundException("Risk event not found")
    old = row.status
    row.status = status
    row.reviewed_by = actor.user_id
    row.reviewed_at = utcnow()
    await audit(db, actor, "AFF_RISK_REVIEWED", "aff_risk_event", event_id, old={"status": old.value}, new={"status": status.value}, note=note)
    return row
