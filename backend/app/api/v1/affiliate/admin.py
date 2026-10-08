"""Affiliate back office API (/api/v1/aff/admin/...). Every route is permission-gated."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate import analytics, commission, ingest, ledger, risk, serialize, settlement, stats, withdrawals
from app.affiliate import content as content_service
from app.affiliate import partners as partner_service
from app.affiliate import security as sec
from app.affiliate import settings as aff_settings
from app.affiliate.common import Actor, actor_from, audit
from app.affiliate.constants import (
    ApprovalStatus,
    AttributionType,
    Bucket,
    ContentStatus,
    DealType,
    Direction,
    DomainStatus,
    IngestEventType,
    IngestStatus,
    LedgerType,
    MaterialType,
    PartnerStatus,
    RecordStatus,
    RiskStatus,
    SignupSource,
    WithdrawalStatus,
)
from app.affiliate.util import client_ip, money, money_out, rate, utcnow
from app.core.constants import PermissionCode as P
from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.exceptions import BadRequestException, ConflictException, ForbiddenException, NotFoundException
from app.models.affiliate import (
    AffBlogPost,
    AffCampaign,
    AffCommission,
    AffCommissionPlan,
    AffContact,
    AffCustomer,
    AffDeposit,
    AffFaq,
    AffFxRate,
    AffIngestEvent,
    AffManualAdjustment,
    AffPartner,
    AffPartnerDeal,
    AffPartnerProfile,
    AffPrMaterial,
    AffRegistration,
    AffRiskEvent,
    AffSettlementPeriod,
    AffSource,
    AffTermsVersion,
    AffTrackingClick,
    AffTrackingDomain,
    AffTrackingLink,
    AffWallet,
    AffWalletTransaction,
    AffWithdrawal,
)
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User
from app.schemas.affiliate import (
    AdjustmentIn,
    BlogIn,
    CampaignUpdateIn,
    ContactReplyIn,
    CsvImportIn,
    DealChangeIn,
    DecisionIn,
    DomainIn,
    FaqIn,
    FraudIn,
    FreezeIn,
    FxRateIn,
    IpFraudIn,
    LinkIn,
    LinkUpdateIn,
    ManualAttributionIn,
    MaterialIn,
    PartnerCreateIn,
    PartnerUpdateIn,
    PeriodReopenIn,
    PlanIn,
    RiskReviewIn,
    SettingsIn,
    SourceIn,
    SourceUpdateIn,
    StatusIn,
    TermsIn,
    WithdrawalActionIn,
)

router = APIRouter(prefix="/aff/admin", tags=["Affiliate admin"])

_FINANCE_TARGETS = ("aff_withdrawal", "aff_partner_deal", "aff_settlement_period", "aff_manual_adjustment", "aff_commission",
                    "aff_withdrawal_method")


def _actor(user: CurrentUser, request: Request) -> Actor:
    return actor_from(user, client_ip(request))


def _page(rows: List[Any], limit: int) -> Dict[str, Any]:
    return {"has_more": len(rows) > limit}


# ===================================================================== overview


@router.get("/overview")
async def overview(user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    by_status = dict((await db.execute(select(AffPartner.status, func.count()).group_by(AffPartner.status))).all())
    open_wd = (await db.execute(select(func.count(), func.coalesce(func.sum(AffWithdrawal.amount), 0)).where(
        AffWithdrawal.status.in_(["PENDING", "UNDER_REVIEW", "APPROVED", "PROCESSING"])))).one()
    failed_ingest = (await db.execute(select(func.count()).select_from(AffIngestEvent).where(AffIngestEvent.status == IngestStatus.FAILED))).scalar_one()
    open_risk = (await db.execute(select(func.count()).select_from(AffRiskEvent).where(AffRiskEvent.status == RiskStatus.OPEN))).scalar_one()
    balances = (await db.execute(select(func.coalesce(func.sum(AffWallet.available_balance), 0), func.coalesce(func.sum(AffWallet.pending_balance), 0),
                                        func.coalesce(func.sum(AffWallet.reserved_balance), 0)))).one()
    pending_adj = (await db.execute(select(func.count()).select_from(AffManualAdjustment).where(AffManualAdjustment.status == ApprovalStatus.PENDING))).scalar_one()
    period = await commission.ensure_current_period(db)
    await db.commit()
    month = await stats.grouped(db, [pid for (pid,) in (await db.execute(select(AffPartner.id))).all()] or [0], "UTC", "this_month", "day")
    return {
        "partners": {(k.value if hasattr(k, "value") else k): v for k, v in by_status.items()},
        "open_withdrawals": {"count": open_wd[0], "amount": money_out(open_wd[1])},
        "failed_ingest": failed_ingest, "open_risk_events": open_risk, "pending_adjustments": pending_adj,
        "balances": {"available": money_out(balances[0]), "pending": money_out(balances[1]), "reserved": money_out(balances[2])},
        "current_period": serialize.period(period),
        "this_month": month,
    }


# ===================================================================== partners


@router.get("/partners")
async def list_partners(status: Optional[str] = None, q: Optional[str] = None, subpartners_only: bool = False,
                        parent_id: Optional[int] = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                        user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    found = await partner_service.search_partners(db, status=status, q=q, parent_id=parent_id,
                                                  has_parent=True if subpartners_only else None, limit=limit, offset=offset)
    ids = [p.id for p, _e in found["rows"]]
    wallets = {w.partner_id: w for w in (await db.execute(select(AffWallet).where(AffWallet.partner_id.in_(ids or [0])))).scalars()}
    items = []
    for p, email in found["rows"]:
        deal = await partner_service.current_deal(db, p.id)
        items.append({**serialize.partner(p, email), "wallet": serialize.wallet(wallets[p.id]) if p.id in wallets else None,
                      "deal": serialize.deal(deal)})
    return {"total": found["total"], "items": items}


@router.post("/partners", status_code=201)
async def create_partner(body: PartnerCreateIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_MANAGE)),
                         db: AsyncSession = Depends(get_db)) -> dict:
    actor = _actor(user, request)
    if body.password:
        await sec.check_password(body.password, str(body.email))
    if body.deal.model_dump(exclude_unset=True) and not actor.can(P.AFF_DEAL_MANAGE.value):
        # ADMIN creates partners; only finance / super admin choose non-default terms
        if any(v is not None for k, v in body.deal.model_dump().items() if k != "plan_id"):
            raise ForbiddenException("Only finance can set custom deal terms; pick a plan instead")
    created = await partner_service.create_partner(
        db, actor, email=str(body.email), password=body.password, signup_source=SignupSource.ADMIN, status=PartnerStatus.ACTIVE,
        profile=body.profile.model_dump(), deal=body.deal.model_dump(exclude_none=True), parent_partner_id=body.parent_partner_id,
        manager_id=body.manager_id, timezone_name=body.timezone or "UTC", email_verified=True,
    )
    await db.commit()
    if not body.password and body.send_set_password_email:
        from app.services.auth_service import AuthService

        try:
            await AuthService(db).forgot_password(str(body.email))
        except Exception:
            pass
    link = created["link"]
    return {"partner": serialize.partner(created["partner"], str(body.email)),
            "default_link": serialize.link(link, await partner_service.link_urls(db, link.link_code))}


@router.get("/partners/{partner_id}")
async def partner_detail(partner_id: int, user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_READ)),
                         db: AsyncSession = Depends(get_db)) -> dict:
    p = await partner_service.get_partner(db, partner_id)
    owner = await db.get(User, p.user_id)
    profile = (await db.execute(select(AffPartnerProfile).where(AffPartnerProfile.partner_id == p.id))).scalar_one_or_none()
    deals = (await db.execute(select(AffPartnerDeal).where(AffPartnerDeal.partner_id == p.id).order_by(AffPartnerDeal.effective_from.desc()))).scalars().all()
    base = await partner_service.link_base(db)
    links = await partner_service.list_links(db, [p.id])
    sources = (await db.execute(select(AffSource).where(AffSource.partner_id == p.id))).scalars().all()
    campaigns = (await db.execute(select(AffCampaign).where(AffCampaign.partner_id == p.id))).scalars().all()
    subs = (await db.execute(select(AffPartner).where(AffPartner.parent_partner_id == p.id))).scalars().all()
    recent_wd = (await db.execute(select(AffWithdrawal).where(AffWithdrawal.partner_id == p.id).order_by(AffWithdrawal.id.desc()).limit(10))).scalars().all()
    manager = await db.get(User, p.manager_id) if p.manager_id else None
    return {
        "partner": serialize.partner(p, owner.email if owner else None),
        "name": owner.full_name if owner else None, "email_verified": owner.is_verified if owner else False,
        "manager": {"id": manager.id, "name": manager.full_name or manager.username, "email": manager.email} if manager else None,
        "profile": serialize.profile(profile),
        "wallet": serialize.wallet(await ledger.get_wallet(db, p.id)),
        "deal": serialize.deal(await partner_service.current_deal(db, p.id)),
        "deal_history": [serialize.deal(d) for d in deals],
        "links": [serialize.link(l, await partner_service.link_urls(db, l.link_code, base)) for l in links],
        "sources": [serialize.source(s) for s in sources],
        "campaigns": [serialize.campaign(c) for c in campaigns],
        "subpartners": [serialize.partner(s) for s in subs],
        "withdrawals": [serialize.withdrawal(w) for w in recent_wd],
        "stats": await stats.summary(db, p, "all", use_cache=False),
        "invite_link": await partner_service.invite_link(db, p) if p.parent_partner_id is None else None,
    }


@router.patch("/partners/{partner_id}")
async def update_partner(partner_id: int, body: PartnerUpdateIn, request: Request,
                         user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    p = await partner_service.get_partner(db, partner_id)
    data = body.model_dump(exclude_unset=True)
    old = {"manager_id": p.manager_id, "subpartner_rate": str(p.subpartner_rate), "timezone": p.timezone, "parent_partner_id": p.parent_partner_id}
    if "manager_id" in data:
        if data["manager_id"]:
            manager = await db.get(User, data["manager_id"])
            if manager is None or (manager.role and manager.role.name in ("USER", "PARTNER")):
                raise BadRequestException("The manager must be a staff user")
        p.manager_id = data["manager_id"] or None
    if data.get("subpartner_rate") is not None:
        p.subpartner_rate = rate(data["subpartner_rate"])
    if data.get("timezone"):
        stats.tz_of(data["timezone"])
        p.timezone = data["timezone"]
    if "parent_partner_id" in data:
        parent_id = data["parent_partner_id"]
        if parent_id == p.id:
            raise BadRequestException("A partner cannot be its own master")
        if parent_id:
            parent = await partner_service.get_partner(db, parent_id)
            if parent.parent_partner_id is not None:
                raise BadRequestException("Only one subpartner level is allowed")
            has_children = (await db.execute(select(AffPartner.id).where(AffPartner.parent_partner_id == p.id).limit(1))).first()
            if has_children:
                raise BadRequestException("This partner has subpartners and cannot become one")
        p.parent_partner_id = parent_id or None
    if body.profile is not None:
        profile = (await db.execute(select(AffPartnerProfile).where(AffPartnerProfile.partner_id == p.id))).scalar_one()
        for key, value in body.profile.model_dump(exclude_unset=True).items():
            setattr(profile, key, value)
    await audit(db, _actor(user, request), "AFF_PARTNER_UPDATED", "aff_partner", p.id, old=old,
                new={k: v for k, v in data.items() if k != "profile"})
    await db.commit()
    return serialize.partner(p)


@router.post("/partners/{partner_id}/status")
async def partner_status(partner_id: int, body: StatusIn, request: Request,
                         user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    p = await partner_service.set_status(db, _actor(user, request), partner_id, PartnerStatus(body.status), body.reason)
    await db.commit()
    return serialize.partner(p)


@router.post("/partners/{partner_id}/impersonate")
async def impersonate(partner_id: int, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_IMPERSONATE)),
                      db: AsyncSession = Depends(get_db)) -> dict:
    return await sec.impersonation_token(db, _actor(user, request), partner_id)


@router.post("/partners/{partner_id}/deal")
async def change_deal(partner_id: int, body: DealChangeIn, request: Request,
                      user: CurrentUser = Depends(require_permission(P.AFF_DEAL_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    data = body.model_dump(exclude_none=True, exclude={"effective_from"})
    deal = await partner_service.set_deal(db, _actor(user, request), partner_id, data, body.effective_from)
    p = await partner_service.get_partner(db, partner_id)
    from app.affiliate.common import notify

    await notify(db, p.user_id, "Your deal changed",
                 f"From {deal.effective_from:%d %b %Y}: {deal.deal_type.value.title()}"
                 + (f", revshare {Decimal(deal.revshare_rate) * 100:.2f}%" if deal.revshare_rate else "")
                 + (f", CPA {money(deal.cpa_amount):.2f} $" if deal.cpa_amount else ""))
    await db.commit()
    return serialize.deal(deal)


@router.get("/partners/{partner_id}/ledger")
async def partner_ledger(partner_id: int, cursor: Optional[int] = None, limit: int = Query(50, ge=1, le=200),
                         user: CurrentUser = Depends(require_permission(P.AFF_FINANCE_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    wallet = await ledger.get_wallet(db, partner_id)
    query = select(AffWalletTransaction).where(AffWalletTransaction.wallet_id == wallet.id)
    if cursor:
        query = query.where(AffWalletTransaction.id < cursor)
    rows = (await db.execute(query.order_by(AffWalletTransaction.id.desc()).limit(limit + 1))).scalars().all()
    return {"wallet": serialize.wallet(wallet), "items": [serialize.ledger_entry(t) for t in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


@router.get("/staff")
async def staff(user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(User).join(Role, Role.id == User.role_id).where(Role.name.not_in(["USER", "PARTNER"]), User.is_active.is_(True))
                             .order_by(User.username))).scalars().all()
    return {"items": [{"id": u.id, "name": u.full_name or u.username, "email": u.email} for u in rows]}


@router.post("/attribution/manual")
async def manual_attribution(body: ManualAttributionIn, request: Request,
                             user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    partner = await partner_service.get_partner(db, body.partner_id)
    customer = (await db.execute(select(AffCustomer).where(AffCustomer.external_customer_id == body.external_customer_id))).scalar_one_or_none()
    if customer is None:
        customer = AffCustomer(external_customer_id=body.external_customer_id, country=(body.country or "").upper() or None)
        db.add(customer)
        await db.flush()
    if (await db.execute(select(AffRegistration.id).where(AffRegistration.customer_id == customer.id))).first():
        raise ConflictException("This customer is already attributed (attribution is frozen)")
    link = None
    if body.tracking_link_id:
        link = await db.get(AffTrackingLink, body.tracking_link_id)
        if link is None or link.partner_id != partner.id:
            raise BadRequestException("The link belongs to another partner")
    reg = AffRegistration(customer_id=customer.id, partner_id=partner.id, source_id=link.source_id if link else None,
                          campaign_id=link.campaign_id if link else None, tracking_link_id=link.id if link else None,
                          attribution_type=AttributionType.MANUAL, country=customer.country, registered_at=utcnow())
    db.add(reg)
    await db.flush()
    await audit(db, _actor(user, request), "AFF_MANUAL_ATTRIBUTION", "aff_registration", reg.id,
                new={"customer": body.external_customer_id, "partner_id": partner.id}, reason=body.reason)
    await db.commit()
    await analytics.mark_dirty(db, partner.id, reg.registered_at)
    return serialize.registration(reg, body.external_customer_id)


# ===================================================================== tracking (any partner)


@router.get("/tracking-links")
async def admin_links(partner_id: Optional[int] = None, q: Optional[str] = None, limit: int = Query(100, ge=1, le=500),
                      user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AffTrackingLink)
    if partner_id:
        query = query.where(AffTrackingLink.partner_id == partner_id)
    if q:
        query = query.where(or_(AffTrackingLink.link_code == q.strip().upper(), func.lower(AffTrackingLink.name).like(f"%{q.lower()}%")))
    rows = (await db.execute(query.order_by(AffTrackingLink.id.desc()).limit(limit))).scalars().all()
    base = await partner_service.link_base(db)
    return {"items": [serialize.link(l, await partner_service.link_urls(db, l.link_code, base)) for l in rows]}


@router.post("/partners/{partner_id}/tracking-links", status_code=201)
async def admin_create_link(partner_id: int, body: LinkIn, request: Request,
                            user: CurrentUser = Depends(require_permission(P.AFF_TRACKING_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    row = await partner_service.create_link(db, _actor(user, request), partner_id, body.model_dump())
    await db.commit()
    return serialize.link(row, await partner_service.link_urls(db, row.link_code))


@router.patch("/tracking-links/{link_id}")
async def admin_update_link(link_id: int, body: LinkUpdateIn, request: Request,
                            user: CurrentUser = Depends(require_permission(P.AFF_TRACKING_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    row = await partner_service.update_link(db, _actor(user, request), None, link_id, body.model_dump(exclude_unset=True))
    await db.commit()
    return serialize.link(row, await partner_service.link_urls(db, row.link_code))


@router.get("/sources")
async def admin_sources(partner_id: Optional[int] = None, user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_READ)),
                        db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AffSource)
    if partner_id:
        query = query.where(AffSource.partner_id == partner_id)
    rows = (await db.execute(query.order_by(AffSource.id.desc()).limit(500))).scalars().all()
    return {"items": [serialize.source(s) for s in rows]}


@router.post("/partners/{partner_id}/sources", status_code=201)
async def admin_create_source(partner_id: int, body: SourceIn, request: Request,
                              user: CurrentUser = Depends(require_permission(P.AFF_TRACKING_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    await partner_service.get_partner(db, partner_id)
    row = await partner_service.create_source(db, _actor(user, request), partner_id, body.model_dump())
    await db.commit()
    return serialize.source(row)


@router.patch("/sources/{source_id}")
async def admin_update_source(source_id: int, body: SourceUpdateIn, request: Request,
                              user: CurrentUser = Depends(require_permission(P.AFF_TRACKING_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    row = await partner_service.update_source(db, _actor(user, request), None, source_id, body.model_dump(exclude_unset=True))
    await db.commit()
    return serialize.source(row)


@router.get("/campaigns")
async def admin_campaigns(partner_id: Optional[int] = None, user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_READ)),
                          db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AffCampaign)
    if partner_id:
        query = query.where(AffCampaign.partner_id == partner_id)
    rows = (await db.execute(query.order_by(AffCampaign.id.desc()).limit(500))).scalars().all()
    return {"items": [serialize.campaign(c) for c in rows]}


@router.patch("/campaigns/{campaign_id}")
async def admin_update_campaign(campaign_id: int, body: CampaignUpdateIn, request: Request,
                                user: CurrentUser = Depends(require_permission(P.AFF_TRACKING_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    row = await partner_service.update_campaign(db, _actor(user, request), None, campaign_id, body.model_dump(exclude_unset=True))
    await db.commit()
    return serialize.campaign(row)


# ===================================================================== tracking domains (super admin)


@router.get("/tracking-domains")
async def domains(user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffTrackingDomain).order_by(AffTrackingDomain.is_primary.desc(), AffTrackingDomain.id))).scalars().all()
    return {"items": [serialize.domain(d) for d in rows], "link_base": await partner_service.link_base(db)}


@router.post("/tracking-domains", status_code=201)
async def add_domain(body: DomainIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_DOMAIN_MANAGE)),
                     db: AsyncSession = Depends(get_db)) -> dict:
    row = await partner_service.upsert_domain(db, _actor(user, request), body.domain, body.is_primary, DomainStatus(body.status))
    await db.commit()
    return serialize.domain(row)


@router.patch("/tracking-domains/{domain_id}")
async def edit_domain(domain_id: int, body: DomainIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_DOMAIN_MANAGE)),
                      db: AsyncSession = Depends(get_db)) -> dict:
    row = await partner_service.upsert_domain(db, _actor(user, request), body.domain, body.is_primary, DomainStatus(body.status), domain_id)
    await db.commit()
    return serialize.domain(row)


@router.post("/tracking-domains/{domain_id}/check")
async def check_domain(domain_id: int, user: CurrentUser = Depends(require_permission(P.AFF_DOMAIN_MANAGE)),
                       db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(AffTrackingDomain, domain_id)
    if row is None:
        raise NotFoundException("Tracking domain not found")
    await partner_service.check_domain(db, row)
    await db.commit()
    return serialize.domain(row)


# ===================================================================== plans & deals


@router.get("/plans")
async def plans(user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffCommissionPlan).order_by(AffCommissionPlan.id))).scalars().all()
    return {"items": [serialize.plan(p) for p in rows]}


async def _save_plan(db: AsyncSession, row: AffCommissionPlan, body: PlanIn) -> None:
    terms = partner_service.deal_terms({"deal_type": body.deal_type, "revshare_rate": body.default_revshare_rate,
                                        "cpa_amount": body.default_cpa_amount, "min_ftd_amount": body.min_ftd_amount,
                                        "hold_days": body.hold_days, "carryover": body.carryover, "tier_table": body.tier_table})
    row.name, row.deal_type = body.name.strip(), terms["deal_type"]
    row.default_revshare_rate, row.default_cpa_amount = terms["revshare_rate"], terms["cpa_amount"]
    row.min_ftd_amount, row.hold_days, row.carryover = terms["min_ftd_amount"], terms["hold_days"], terms["carryover"]
    row.tier_table, row.description, row.status = terms["tier_table"], body.description, RecordStatus(body.status)


@router.post("/plans", status_code=201)
async def create_plan(body: PlanIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_DEAL_MANAGE)),
                      db: AsyncSession = Depends(get_db)) -> dict:
    if (await db.execute(select(AffCommissionPlan.id).where(AffCommissionPlan.name == body.name.strip()))).first():
        raise ConflictException("A plan with this name exists")
    row = AffCommissionPlan(name=body.name, deal_type=DealType(body.deal_type))
    await _save_plan(db, row, body)
    db.add(row)
    await db.flush()
    await audit(db, _actor(user, request), "AFF_PLAN_CREATED", "aff_commission_plan", row.id, new=serialize.plan(row))
    await db.commit()
    return serialize.plan(row)


@router.put("/plans/{plan_id}")
async def update_plan(plan_id: int, body: PlanIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_DEAL_MANAGE)),
                      db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(AffCommissionPlan, plan_id)
    if row is None:
        raise NotFoundException("Plan not found")
    old = serialize.plan(row)
    await _save_plan(db, row, body)
    await audit(db, _actor(user, request), "AFF_PLAN_UPDATED", "aff_commission_plan", row.id, old=old, new=serialize.plan(row))
    await db.commit()
    return serialize.plan(row)


@router.get("/deals")
async def recent_deals(limit: int = Query(100, ge=1, le=500), user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_READ)),
                       db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffPartnerDeal, AffPartner.partner_code).join(AffPartner, AffPartner.id == AffPartnerDeal.partner_id)
                             .order_by(AffPartnerDeal.id.desc()).limit(limit))).all()
    return {"items": [{**serialize.deal(d), "partner_id": d.partner_id, "partner_code": code} for d, code in rows]}


# ===================================================================== statistics


@router.get("/statistics")
async def admin_statistics(group_by: str = "partner", period: str = "30d", date_from: Optional[date] = None,
                           date_to: Optional[date] = None, partner_ids: Optional[str] = None, countries: Optional[str] = None,
                           user: CurrentUser = Depends(require_permission(P.AFF_STATS_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    ids = [int(x) for x in (partner_ids or "").split(",") if x.strip().isdigit()]
    if not ids:
        ids = [pid for (pid,) in (await db.execute(select(AffPartner.id))).all()] or [0]
    rows = await stats.grouped(db, ids, "UTC", period, group_by, date_from, date_to,
                               countries=[c for c in (countries or "").upper().split(",") if len(c) == 2])
    return {"group_by": group_by, "items": rows}


@router.get("/statistics/export")
async def admin_statistics_export(group_by: str = "partner", period: str = "30d", date_from: Optional[date] = None,
                                  date_to: Optional[date] = None, user: CurrentUser = Depends(require_permission(P.AFF_STATS_READ)),
                                  db: AsyncSession = Depends(get_db)) -> Response:
    ids = [pid for (pid,) in (await db.execute(select(AffPartner.id))).all()] or [0]
    rows = await stats.grouped(db, ids, "UTC", period, group_by, date_from, date_to)
    return Response(stats.to_csv(rows), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="affiliate-{group_by}-{period}.csv"'})


@router.post("/analytics/rebuild")
async def rebuild_analytics(days: int = Query(2, ge=1, le=400), user: CurrentUser = Depends(require_permission(P.AFF_INGEST_MANAGE)),
                            db: AsyncSession = Depends(get_db)) -> dict:
    from datetime import timedelta

    written = await analytics.rebuild(db, utcnow() - timedelta(days=days - 1))
    return {"rows": written}


# ===================================================================== settlement


@router.get("/periods")
async def periods(limit: int = Query(30, ge=1, le=200), user: CurrentUser = Depends(require_permission(P.AFF_FINANCE_READ)),
                  db: AsyncSession = Depends(get_db)) -> dict:
    await commission.ensure_current_period(db)
    await db.commit()
    rows = (await db.execute(select(AffSettlementPeriod).order_by(AffSettlementPeriod.start_date.desc()).limit(limit))).scalars().all()
    return {"items": [serialize.period(p) for p in rows]}


@router.get("/periods/{period_id}/preview")
async def period_preview(period_id: int, user: CurrentUser = Depends(require_permission(P.AFF_FINANCE_READ)),
                         db: AsyncSession = Depends(get_db)) -> dict:
    data = await settlement.preview(db, period_id)
    codes = dict((await db.execute(select(AffPartner.id, AffPartner.partner_code))).all())
    return {"period": serialize.period(data["period"]), "total_to_settle": money_out(data["total_to_settle"]),
            "held_total": money_out(data["held_total"]),
            "partners": [{"partner_id": r["partner_id"], "partner_code": codes.get(r["partner_id"]), "cpa": money_out(r["cpa"]),
                          "revshare": money_out(r["revshare"]), "held": money_out(r["held"]), "count": r["count"]} for r in data["partners"]]}


@router.post("/periods/{period_id}/close")
async def close_period(period_id: int, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_SETTLEMENT_MANAGE)),
                       db: AsyncSession = Depends(get_db)) -> dict:
    return await settlement.close_period(db, _actor(user, request), period_id)


@router.post("/periods/{period_id}/reopen")
async def reopen_period(period_id: int, body: PeriodReopenIn, request: Request,
                        user: CurrentUser = Depends(require_permission(P.AFF_SETTLEMENT_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    return serialize.period(await settlement.reopen_period(db, _actor(user, request), period_id, body.reason))


@router.get("/periods/{period_id}/statements")
async def period_statements(period_id: int, user: CurrentUser = Depends(require_permission(P.AFF_FINANCE_READ)),
                            db: AsyncSession = Depends(get_db)) -> dict:
    from app.models.affiliate import AffPartnerPeriodBalance

    rows = (await db.execute(select(AffPartnerPeriodBalance, AffPartner.partner_code).join(AffPartner, AffPartner.id == AffPartnerPeriodBalance.partner_id)
                             .where(AffPartnerPeriodBalance.period_id == period_id))).all()
    return {"items": [{**serialize.period_balance(b), "partner_code": code} for b, code in rows]}


# ===================================================================== wallets, commissions


@router.get("/wallets")
async def wallets(q: Optional[str] = None, negative_only: bool = False, limit: int = Query(100, ge=1, le=500),
                  user: CurrentUser = Depends(require_permission(P.AFF_FINANCE_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AffWallet, AffPartner.partner_code, AffPartner.payout_frozen).join(AffPartner, AffPartner.id == AffWallet.partner_id)
    if q:
        query = query.where(AffPartner.partner_code == q.strip().upper())
    if negative_only:
        query = query.where(AffWallet.available_balance < 0)
    rows = (await db.execute(query.order_by(AffWallet.available_balance.desc()).limit(limit))).all()
    return {"items": [{**serialize.wallet(w), "partner_id": w.partner_id, "partner_code": code, "payout_frozen": frozen}
                      for w, code, frozen in rows]}


@router.post("/wallets/reconcile")
async def reconcile(user: CurrentUser = Depends(require_permission(P.AFF_FINANCE_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    mismatches = await ledger.reconcile(db)
    await db.commit()
    return {"mismatches": mismatches}


@router.get("/commissions")
async def commissions(partner_id: Optional[int] = None, period_id: Optional[int] = None, status: Optional[str] = None,
                      limit: int = Query(100, ge=1, le=500), user: CurrentUser = Depends(require_permission(P.AFF_FINANCE_READ)),
                      db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AffCommission)
    if partner_id:
        query = query.where(AffCommission.partner_id == partner_id)
    if period_id:
        query = query.where(AffCommission.period_id == period_id)
    if status:
        query = query.where(AffCommission.status == status.upper())
    rows = (await db.execute(query.order_by(AffCommission.id.desc()).limit(limit))).scalars().all()
    return {"items": [serialize.commission(c) for c in rows]}


# ===================================================================== withdrawals queue


@router.get("/withdrawals")
async def withdrawal_queue(status: Optional[str] = None, partner_id: Optional[int] = None, limit: int = Query(100, ge=1, le=500),
                           user: CurrentUser = Depends(require_permission(P.AFF_FINANCE_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AffWithdrawal, AffPartner.partner_code, AffPartner.payout_frozen).join(AffPartner, AffPartner.id == AffWithdrawal.partner_id)
    if status:
        query = query.where(AffWithdrawal.status.in_([s.strip().upper() for s in status.split(",")]))
    if partner_id:
        query = query.where(AffWithdrawal.partner_id == partner_id)
    rows = (await db.execute(query.order_by(AffWithdrawal.requested_at.desc()).limit(limit))).all()
    return {"items": [{**serialize.withdrawal(w), "partner_code": code, "payout_frozen": frozen} for w, code, frozen in rows]}


@router.get("/withdrawals/export")
async def export_withdrawals(request: Request, status: str = "APPROVED",
                             user: CurrentUser = Depends(require_permission(P.AFF_WITHDRAWAL_MANAGE)),
                             db: AsyncSession = Depends(get_db)) -> Response:
    body = await withdrawals.export_csv(db, _actor(user, request), WithdrawalStatus(status.upper()))
    await db.commit()
    return Response(body, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="partner-payouts-{status.lower()}.csv"'})


@router.get("/withdrawals/{withdrawal_id}")
async def withdrawal_detail(withdrawal_id: int, user: CurrentUser = Depends(require_permission(P.AFF_FINANCE_READ)),
                            db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(AffWithdrawal, withdrawal_id)
    if row is None:
        raise NotFoundException("Withdrawal not found")
    return {**serialize.withdrawal(row), "history": [serialize.status_history(h) for h in await withdrawals.history(db, row.id)]}


_ACTIONS = {"review": WithdrawalStatus.UNDER_REVIEW, "approve": WithdrawalStatus.APPROVED, "processing": WithdrawalStatus.PROCESSING,
            "mark-paid": WithdrawalStatus.COMPLETED, "reject": WithdrawalStatus.REJECTED, "fail": WithdrawalStatus.FAILED}


@router.post("/withdrawals/{withdrawal_id}/{action}")
async def withdrawal_action(withdrawal_id: int, action: str, body: WithdrawalActionIn, request: Request,
                            user: CurrentUser = Depends(require_permission(P.AFF_WITHDRAWAL_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    if action not in _ACTIONS:
        raise NotFoundException("Unknown action")
    row = await withdrawals.transition(db, _actor(user, request), withdrawal_id, _ACTIONS[action], note=body.note,
                                       external_reference=body.external_payment_reference)
    await db.commit()
    return serialize.withdrawal(row)


# ===================================================================== manual adjustments (maker-checker)


@router.get("/adjustments")
async def adjustments(status: Optional[str] = None, user: CurrentUser = Depends(require_permission(P.AFF_FINANCE_READ)),
                      db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AffManualAdjustment, AffPartner.partner_code).join(AffPartner, AffPartner.id == AffManualAdjustment.partner_id)
    if status:
        query = query.where(AffManualAdjustment.status == status.upper())
    rows = (await db.execute(query.order_by(AffManualAdjustment.id.desc()).limit(200))).all()
    return {"items": [{**serialize.adjustment(a), "partner_code": code} for a, code in rows]}


@router.post("/adjustments", status_code=201)
async def request_adjustment(body: AdjustmentIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_ADJUST)),
                             db: AsyncSession = Depends(get_db)) -> dict:
    await partner_service.get_partner(db, body.partner_id)
    amount = money(body.amount)
    if amount <= 0:
        raise BadRequestException("Enter a positive amount")
    row = AffManualAdjustment(partner_id=body.partner_id, direction=Direction(body.direction), amount=amount, reason=body.reason,
                              requested_by=user.id)
    db.add(row)
    await db.flush()
    await audit(db, _actor(user, request), "AFF_ADJUSTMENT_REQUESTED", "aff_manual_adjustment", row.id, new=serialize.adjustment(row))
    await db.commit()
    return serialize.adjustment(row)


@router.post("/adjustments/{adjustment_id}/decide")
async def decide_adjustment(adjustment_id: int, body: DecisionIn, request: Request,
                            user: CurrentUser = Depends(require_permission(P.AFF_ADJUST)), db: AsyncSession = Depends(get_db)) -> dict:
    row = (await db.execute(select(AffManualAdjustment).where(AffManualAdjustment.id == adjustment_id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise NotFoundException("Adjustment not found")
    if row.status != ApprovalStatus.PENDING:
        raise ConflictException("This adjustment was already decided")
    if row.requested_by == user.id:
        raise ForbiddenException("A second person must approve an adjustment (maker-checker)")
    actor = _actor(user, request)
    row.status = ApprovalStatus.APPROVED if body.approve else ApprovalStatus.REJECTED
    row.approved_by = user.id
    row.decided_at = utcnow()
    row.decision_note = body.note
    if body.approve:
        wallet = await ledger.lock_wallet(db, row.partner_id)
        delta = money(row.amount) if row.direction == Direction.CREDIT else -money(row.amount)
        await ledger.post(db, wallet, entry_type=LedgerType.MANUAL_ADJUSTMENT, bucket=Bucket.AVAILABLE, delta=delta,
                          key=f"adj:{row.id}", reference_type="manual_adjustment", reference_id=row.id, description=row.reason,
                          created_by=user.id)
        partner = await db.get(AffPartner, row.partner_id)
        from app.affiliate.common import notify

        await notify(db, partner.user_id, "Balance adjusted", f"{delta:+.2f} $: {row.reason}")
    await audit(db, actor, "AFF_ADJUSTMENT_APPROVED" if body.approve else "AFF_ADJUSTMENT_REJECTED", "aff_manual_adjustment", row.id,
                new=serialize.adjustment(row))
    await db.commit()
    return serialize.adjustment(row)


# ===================================================================== risk


@router.get("/risk-events")
async def risk_events(status: Optional[str] = "OPEN", severity: Optional[str] = None, partner_id: Optional[int] = None,
                      user: CurrentUser = Depends(require_permission(P.AFF_RISK_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AffRiskEvent)
    if status:
        query = query.where(AffRiskEvent.status == status.upper())
    if severity:
        query = query.where(AffRiskEvent.severity == severity.upper())
    if partner_id:
        query = query.where(AffRiskEvent.partner_id == partner_id)
    rows = (await db.execute(query.order_by(AffRiskEvent.id.desc()).limit(200))).scalars().all()
    return {"items": [serialize.risk(r) for r in rows]}


@router.post("/risk-events/{event_id}/review")
async def review_risk(event_id: int, body: RiskReviewIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_RISK_MANAGE)),
                      db: AsyncSession = Depends(get_db)) -> dict:
    row = await risk.review_event(db, _actor(user, request), event_id, RiskStatus(body.status), body.note)
    await db.commit()
    return serialize.risk(row)


@router.post("/partners/{partner_id}/freeze")
async def freeze(partner_id: int, body: FreezeIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_RISK_MANAGE)),
                 db: AsyncSession = Depends(get_db)) -> dict:
    await risk.set_payout_freeze(db, _actor(user, request), partner_id, body.frozen, body.reason)
    await db.commit()
    return {"partner_id": partner_id, "payout_frozen": body.frozen}


@router.post("/deposits/{deposit_id}/fraud")
async def deposit_fraud(deposit_id: int, body: FraudIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_RISK_MANAGE)),
                        db: AsyncSession = Depends(get_db)) -> dict:
    row = await risk.mark_deposit_fraud(db, _actor(user, request), deposit_id, body.reason)
    await db.commit()
    await analytics.mark_dirty(db, row.partner_id, row.completed_at or utcnow())
    return serialize.deposit(row)


@router.post("/registrations/{registration_id}/fraud")
async def registration_fraud(registration_id: int, body: FraudIn, request: Request,
                             user: CurrentUser = Depends(require_permission(P.AFF_RISK_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    row = await risk.mark_registration_fraud(db, _actor(user, request), registration_id, body.reason)
    await db.commit()
    await analytics.mark_dirty(db, row.partner_id, row.registered_at)
    return serialize.registration(row)


@router.post("/clicks/{click_id}/fraud")
async def click_fraud(click_id: str, body: FraudIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_RISK_MANAGE)),
                      db: AsyncSession = Depends(get_db)) -> dict:
    row = await risk.mark_click_fraud(db, _actor(user, request), click_id, body.reason)
    await db.commit()
    await analytics.mark_dirty(db, row.partner_id, row.clicked_at)
    return serialize.click(row)


@router.post("/clicks/fraud-by-ip")
async def ip_fraud(body: IpFraudIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_RISK_MANAGE)),
                   db: AsyncSession = Depends(get_db)) -> dict:
    count = await risk.mark_ip_clicks_fraud(db, _actor(user, request), body.partner_id, body.ip_hash, body.hours, body.reason)
    await db.commit()
    from datetime import timedelta

    await analytics.mark_dirty(db, body.partner_id, utcnow() - timedelta(hours=body.hours))
    return {"marked": count}


@router.get("/clicks")
async def clicks(partner_id: int, limit: int = Query(100, ge=1, le=500), user: CurrentUser = Depends(require_permission(P.AFF_RISK_MANAGE)),
                 db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffTrackingClick).where(AffTrackingClick.partner_id == partner_id)
                             .order_by(AffTrackingClick.clicked_at.desc()).limit(limit))).scalars().all()
    return {"items": [serialize.click(c) for c in rows]}


@router.get("/registrations")
async def registrations(partner_id: Optional[int] = None, limit: int = Query(100, ge=1, le=500),
                        user: CurrentUser = Depends(require_permission(P.AFF_RISK_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AffRegistration, AffCustomer.external_customer_id).join(AffCustomer, AffCustomer.id == AffRegistration.customer_id)
    if partner_id:
        query = query.where(AffRegistration.partner_id == partner_id)
    rows = (await db.execute(query.order_by(AffRegistration.id.desc()).limit(limit))).all()
    return {"items": [serialize.registration(r, ext) for r, ext in rows]}


@router.get("/deposits")
async def deposits(partner_id: Optional[int] = None, first_only: bool = False, limit: int = Query(100, ge=1, le=500),
                   user: CurrentUser = Depends(require_permission(P.AFF_RISK_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AffDeposit)
    if partner_id:
        query = query.where(AffDeposit.partner_id == partner_id)
    if first_only:
        query = query.where(AffDeposit.is_first_deposit.is_(True))
    rows = (await db.execute(query.order_by(AffDeposit.id.desc()).limit(limit))).scalars().all()
    return {"items": [serialize.deposit(d) for d in rows]}


# ===================================================================== ingest monitor


@router.get("/ingest-events")
async def ingest_events(status: Optional[str] = None, event_type: Optional[str] = None, cursor: Optional[int] = None,
                        limit: int = Query(50, ge=1, le=200), user: CurrentUser = Depends(require_permission(P.AFF_INGEST_MANAGE)),
                        db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AffIngestEvent)
    if status:
        query = query.where(AffIngestEvent.status == status.upper())
    if event_type:
        query = query.where(AffIngestEvent.event_type == event_type.upper())
    if cursor:
        query = query.where(AffIngestEvent.id < cursor)
    rows = (await db.execute(query.order_by(AffIngestEvent.id.desc()).limit(limit + 1))).scalars().all()
    counts = dict((await db.execute(select(AffIngestEvent.status, func.count()).group_by(AffIngestEvent.status))).all())
    return {"items": [serialize.ingest_event(e) for e in rows[:limit]], "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
            "counts": {(k.value if hasattr(k, "value") else k): v for k, v in counts.items()}}


@router.get("/ingest-events/{event_id}")
async def ingest_event(event_id: int, user: CurrentUser = Depends(require_permission(P.AFF_INGEST_MANAGE)),
                       db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(AffIngestEvent, event_id)
    if row is None:
        raise NotFoundException("Ingest event not found")
    return serialize.ingest_event(row, with_payload=True)


@router.post("/ingest-events/{event_id}/retry")
async def retry_ingest(event_id: int, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_INGEST_MANAGE)),
                       db: AsyncSession = Depends(get_db)) -> dict:
    row = await ingest.retry_one(db, _actor(user, request), event_id)
    return serialize.ingest_event(row)


@router.post("/ingest/csv")
async def ingest_csv(body: CsvImportIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_INGEST_MANAGE)),
                     db: AsyncSession = Depends(get_db)) -> dict:
    return await ingest.import_csv(db, _actor(user, request), IngestEventType(body.event_type.upper()), body.csv)


@router.get("/fx-rates")
async def fx_rates(user: CurrentUser = Depends(require_permission(P.AFF_FINANCE_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffFxRate).order_by(AffFxRate.rate_date.desc()).limit(200))).scalars().all()
    return {"items": [{"rate_date": r.rate_date.isoformat(), "currency": r.currency, "rate_to_usd": str(r.rate_to_usd)} for r in rows],
            "fallback": await aff_settings.get(db, "fallback_fx_rates")}


@router.post("/fx-rates/sync")
async def sync_fx_rates(request: Request, user: CurrentUser = Depends(require_permission(P.AFF_DEAL_MANAGE)),
                        db: AsyncSession = Depends(get_db)) -> dict:
    from app.affiliate import fx

    try:
        result = await fx.sync_rates(db)
    except Exception as exc:
        raise BadRequestException(f"Could not fetch rates from the ECB source: {exc}") from exc
    await audit(db, _actor(user, request), "AFF_FX_SYNCED", "aff_fx_rate", result["date"], new=result)
    await db.commit()
    return result


@router.post("/fx-rates", status_code=201)
async def set_fx_rate(body: FxRateIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_DEAL_MANAGE)),
                      db: AsyncSession = Depends(get_db)) -> dict:
    value = Decimal(body.rate_to_usd)
    if value <= 0:
        raise BadRequestException("Rate must be positive")
    currency = body.currency.upper()
    row = await db.get(AffFxRate, (body.rate_date, currency))
    if row is None:
        db.add(AffFxRate(rate_date=body.rate_date, currency=currency, rate_to_usd=value))
    else:
        row.rate_to_usd = value
    await audit(db, _actor(user, request), "AFF_FX_RATE_SET", "aff_fx_rate", f"{body.rate_date}:{currency}", new={"rate": str(value)})
    await db.commit()
    return {"rate_date": body.rate_date.isoformat(), "currency": currency, "rate_to_usd": str(value)}


# ===================================================================== content


@router.get("/pr-materials")
async def admin_materials(user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffPrMaterial).order_by(AffPrMaterial.id.desc()))).scalars().all()
    return {"items": [serialize.material(x) for x in rows]}


async def _save_material(row: AffPrMaterial, body: MaterialIn, user_id: str) -> None:
    row.type, row.title, row.description = MaterialType(body.type), body.title, body.description
    row.file_url = content_service.check_media(body.file_url)
    row.body_text, row.width, row.height, row.language = body.body_text, body.width, body.height, body.language
    row.geo = [g.upper() for g in body.geo or []] or None
    row.partner_id, row.campaign_id = body.partner_id, body.campaign_id
    row.status = ContentStatus(body.status)
    if row.status == ContentStatus.PUBLISHED:
        row.reviewed_by = user_id  # publishing = admin review of the material (compliance)


@router.post("/pr-materials", status_code=201)
async def create_material(body: MaterialIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_CONTENT_MANAGE)),
                          db: AsyncSession = Depends(get_db)) -> dict:
    row = AffPrMaterial(type=MaterialType(body.type), title=body.title)
    await _save_material(row, body, user.id)
    db.add(row)
    await db.flush()
    await audit(db, _actor(user, request), "AFF_PR_SAVED", "aff_pr_material", row.id, new={"title": row.title, "status": row.status.value})
    await db.commit()
    return serialize.material(row)


@router.put("/pr-materials/{material_id}")
async def update_material(material_id: int, body: MaterialIn, request: Request,
                          user: CurrentUser = Depends(require_permission(P.AFF_CONTENT_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(AffPrMaterial, material_id)
    if row is None:
        raise NotFoundException("Material not found")
    await _save_material(row, body, user.id)
    await audit(db, _actor(user, request), "AFF_PR_SAVED", "aff_pr_material", row.id, new={"title": row.title, "status": row.status.value})
    await db.commit()
    return serialize.material(row)


@router.get("/faqs")
async def admin_faqs(user: CurrentUser = Depends(require_permission(P.AFF_SUPPORT_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffFaq).order_by(AffFaq.sort_order, AffFaq.id))).scalars().all()
    return {"items": [serialize.faq(f) for f in rows]}


@router.post("/faqs", status_code=201)
async def create_faq(body: FaqIn, user: CurrentUser = Depends(require_permission(P.AFF_SUPPORT_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    row = AffFaq(**{**body.model_dump(), "status": ContentStatus(body.status)})
    db.add(row)
    await db.commit()
    return serialize.faq(row)


@router.put("/faqs/{faq_id}")
async def update_faq(faq_id: int, body: FaqIn, user: CurrentUser = Depends(require_permission(P.AFF_SUPPORT_MANAGE)),
                     db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(AffFaq, faq_id)
    if row is None:
        raise NotFoundException("FAQ not found")
    for key, value in body.model_dump().items():
        setattr(row, key, ContentStatus(value) if key == "status" else value)
    await db.commit()
    return serialize.faq(row)


@router.get("/blog-posts")
async def admin_blog(user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffBlogPost).order_by(AffBlogPost.id.desc()))).scalars().all()
    return {"items": [serialize.blog(b) for b in rows]}


async def _save_blog(db: AsyncSession, row: AffBlogPost, body: BlogIn) -> None:
    row.title, row.excerpt, row.content, row.language = body.title, body.excerpt, body.content, body.language
    row.cover_image = content_service.check_media(body.cover_image)
    status = ContentStatus(body.status)
    if status == ContentStatus.PUBLISHED and row.published_at is None:
        row.published_at = utcnow()
    row.status = status
    row.slug = await content_service.unique_slug(db, body.title, row.id)


@router.post("/blog-posts", status_code=201)
async def create_blog(body: BlogIn, user: CurrentUser = Depends(require_permission(P.AFF_CONTENT_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    row = AffBlogPost(author_id=user.id, title=body.title, slug="pending", content=body.content)
    await _save_blog(db, row, body)
    db.add(row)
    await db.commit()
    return serialize.blog(row)


@router.put("/blog-posts/{post_id}")
async def update_blog(post_id: int, body: BlogIn, user: CurrentUser = Depends(require_permission(P.AFF_CONTENT_MANAGE)),
                      db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(AffBlogPost, post_id)
    if row is None:
        raise NotFoundException("Post not found")
    await _save_blog(db, row, body)
    await db.commit()
    return serialize.blog(row)


@router.get("/contacts")
async def admin_contacts(status: Optional[str] = None, user: CurrentUser = Depends(require_permission(P.AFF_SUPPORT_MANAGE)),
                         db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AffContact, AffPartner.partner_code).outerjoin(AffPartner, AffPartner.id == AffContact.partner_id)
    if status:
        query = query.where(AffContact.status == status.upper())
    rows = (await db.execute(query.order_by(AffContact.id.desc()).limit(200))).all()
    return {"items": [{**serialize.contact(c), "partner_code": code} for c, code in rows]}


@router.patch("/contacts/{contact_id}")
async def reply_contact(contact_id: int, body: ContactReplyIn, request: Request,
                        user: CurrentUser = Depends(require_permission(P.AFF_SUPPORT_MANAGE)), db: AsyncSession = Depends(get_db)) -> dict:
    row = await content_service.reply_contact(db, _actor(user, request), contact_id, body.reply, body.status, body.assigned_to)
    await db.commit()
    return serialize.contact(row)


# ===================================================================== terms, settings, audit


@router.get("/terms")
async def list_terms(user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(AffTermsVersion).order_by(AffTermsVersion.id.desc()))).scalars().all()
    return {"items": [serialize.terms(t, with_content=True) for t in rows]}


@router.post("/terms", status_code=201)
async def publish_terms(body: TermsIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_SETTINGS_MANAGE)),
                        db: AsyncSession = Depends(get_db)) -> dict:
    if (await db.execute(select(AffTermsVersion.id).where(AffTermsVersion.version == body.version))).first():
        raise ConflictException("This version already exists")
    row = AffTermsVersion(version=body.version, content=body.content, content_url=body.content_url, published_at=utcnow())
    db.add(row)
    await db.flush()
    await audit(db, _actor(user, request), "AFF_TERMS_PUBLISHED", "aff_terms_version", row.id, new={"version": body.version})
    await db.commit()
    return serialize.terms(row, with_content=True)


@router.get("/settings")
async def get_settings_(user: CurrentUser = Depends(require_permission(P.AFF_PARTNER_READ)), db: AsyncSession = Depends(get_db)) -> dict:
    return {"values": await aff_settings.get_all(db, fresh=True), "descriptions": aff_settings.describe()}


@router.put("/settings")
async def put_settings(body: SettingsIn, request: Request, user: CurrentUser = Depends(require_permission(P.AFF_SETTINGS_MANAGE)),
                       db: AsyncSession = Depends(get_db)) -> dict:
    old = await aff_settings.get_all(db, fresh=True)
    values = await aff_settings.update(db, body.changes, user.id)
    await audit(db, _actor(user, request), "AFF_SETTINGS_UPDATED", "aff_settings", None,
                old={k: old.get(k) for k in body.changes}, new={k: values.get(k) for k in body.changes})
    await db.commit()
    return {"values": values, "descriptions": aff_settings.describe()}


@router.get("/audit-logs")
async def audit_logs(target_type: Optional[str] = None, target_id: Optional[str] = None, cursor: Optional[str] = None,
                     limit: int = Query(50, ge=1, le=200), user: CurrentUser = Depends(require_permission(P.AUDIT_READ)),
                     db: AsyncSession = Depends(get_db)) -> dict:
    query = select(AuditLog, User.username).outerjoin(User, User.id == AuditLog.actor_id).where(
        or_(AuditLog.target_type.like("aff_%"), AuditLog.action.like("AFF_%")))
    role = user.role.upper()
    if role == "FINANCE_ADMIN":
        query = query.where(AuditLog.target_type.in_(_FINANCE_TARGETS))
    elif role != "SUPERADMIN":
        query = query.where(AuditLog.target_type.not_in(_FINANCE_TARGETS))
    if target_type:
        query = query.where(AuditLog.target_type == target_type)
    if target_id:
        query = query.where(AuditLog.target_id == target_id)
    if cursor:
        query = query.where(AuditLog.created_at < cursor)
    rows = (await db.execute(query.order_by(AuditLog.created_at.desc()).limit(limit))).all()
    return {"items": [{"id": a.id, "actor": name or ("system" if a.actor_id is None else a.actor_id), "action": a.action,
                       "target_type": a.target_type, "target_id": a.target_id, "details": a.details, "ip": a.ip_address,
                       "created_at": serialize._v(a.created_at)} for a, name in rows]}
