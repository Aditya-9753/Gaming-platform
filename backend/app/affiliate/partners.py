"""Partners, deals, sources, campaigns, tracking links, promo codes and tracking domains.

``create_partner`` is the only way a partner comes to exist: one transaction
writes the user, partner (unique partner_code generated here, in this DB),
profile, wallet, deal and the "Default" source + tracking link, so a real
link never exists before its partner row does.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlencode

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate import settings as aff_settings
from app.affiliate.common import Actor, audit, notify
from app.affiliate.constants import (
    DealType,
    DomainStatus,
    PartnerStatus,
    RecordStatus,
    SignupSource,
    SourceType,
)
from app.affiliate.util import money, random_code, rate, utcnow
from app.core.config import get_settings
from app.core.constants import UserRole
from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.core.security import hash_password
from app.models.affiliate import (
    AffCampaign,
    AffCommissionPlan,
    AffPartner,
    AffPartnerDeal,
    AffPartnerProfile,
    AffPromoCode,
    AffSource,
    AffTrackingDomain,
    AffTrackingLink,
    AffWallet,
)
from app.models.role import Role
from app.models.user import User

PROFILE_FIELDS = (
    "first_name", "last_name", "phone", "company_name", "country", "address", "city",
    "state", "postal_code", "telegram", "website", "traffic_description",
)
_DEFAULT_DEAL = {"deal_type": DealType.REVSHARE, "revshare_rate": Decimal("0.5"), "cpa_amount": Decimal("0"),
                 "min_ftd_amount": Decimal("0"), "hold_days": 14, "carryover": True, "tier_table": None}


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


async def get_partner(db: AsyncSession, partner_id: int) -> AffPartner:
    partner = await db.get(AffPartner, partner_id)
    if partner is None:
        raise NotFoundException("Partner not found")
    return partner


async def partner_for_user(db: AsyncSession, user_id: str) -> Optional[AffPartner]:
    return (await db.execute(select(AffPartner).where(AffPartner.user_id == user_id))).scalar_one_or_none()


async def partner_by_code(db: AsyncSession, code: str) -> Optional[AffPartner]:
    return (await db.execute(select(AffPartner).where(AffPartner.partner_code == code.strip().upper()))).scalar_one_or_none()


async def _unique_code(db: AsyncSession, model: Any, column: Any, length: int = 8) -> str:
    for _ in range(12):
        code = random_code(length)
        if (await db.execute(select(model.id).where(column == code))).first() is None:
            # partner codes double as the default link code, so both namespaces must be free
            if model is AffPartner and (await db.execute(select(AffTrackingLink.id).where(AffTrackingLink.link_code == code))).first():
                continue
            if model is AffTrackingLink and (await db.execute(select(AffPartner.id).where(AffPartner.partner_code == code))).first():
                continue
            return code
    raise ConflictException("Could not generate a unique code, try again")


# ---------------------------------------------------------------------------
# Deals
# ---------------------------------------------------------------------------


async def default_plan(db: AsyncSession) -> Optional[AffCommissionPlan]:
    plan_id = int(await aff_settings.get(db, "default_plan_id") or 0)
    if plan_id:
        plan = await db.get(AffCommissionPlan, plan_id)
        if plan and plan.status == RecordStatus.ACTIVE:
            return plan
    return (
        await db.execute(
            select(AffCommissionPlan).where(AffCommissionPlan.status == RecordStatus.ACTIVE).order_by(AffCommissionPlan.id).limit(1)
        )
    ).scalar_one_or_none()


def _validate_tiers(tiers: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, str]]]:
    if not tiers:
        return None
    out = []
    for tier in tiers:
        try:
            threshold = money(tier.get("min_ngr", 0))
            tier_rate = rate(tier["rate"])
        except (KeyError, TypeError) as exc:
            raise BadRequestException("Each tier needs min_ngr and rate") from exc
        out.append({"min_ngr": str(threshold), "rate": str(tier_rate)})
    out.sort(key=lambda t: Decimal(t["min_ngr"]))
    if Decimal(out[0]["min_ngr"]) != 0:
        out.insert(0, {"min_ngr": "0", "rate": out[0]["rate"]})
    return out


def deal_terms(data: Dict[str, Any], plan: Optional[AffCommissionPlan] = None) -> Dict[str, Any]:
    """Normalise deal input (explicit values win over the plan's)."""
    base = dict(_DEFAULT_DEAL)
    if plan is not None:
        base.update(
            deal_type=plan.deal_type, revshare_rate=plan.default_revshare_rate, cpa_amount=plan.default_cpa_amount,
            min_ftd_amount=plan.min_ftd_amount, hold_days=plan.hold_days, carryover=plan.carryover, tier_table=plan.tier_table,
        )
    for key in ("deal_type", "revshare_rate", "cpa_amount", "min_ftd_amount", "hold_days", "carryover", "carryover_cap",
                "cpa_geo_list", "tier_table"):
        if data.get(key) is not None:
            base[key] = data[key]
    deal_type = DealType(base["deal_type"])
    terms = {
        "deal_type": deal_type,
        "revshare_rate": rate(base.get("revshare_rate") or 0),
        "cpa_amount": money(base.get("cpa_amount") or 0),
        "min_ftd_amount": money(base.get("min_ftd_amount") or 0),
        "hold_days": int(base.get("hold_days") or 0),
        "carryover": bool(base.get("carryover", True)),
        "carryover_cap": money(base["carryover_cap"]) if base.get("carryover_cap") not in (None, "") else None,
        "cpa_geo_list": sorted({c.strip().upper() for c in base.get("cpa_geo_list") or [] if c.strip()}) or None,
        "tier_table": _validate_tiers(base.get("tier_table")),
    }
    if terms["cpa_amount"] < 0 or terms["min_ftd_amount"] < 0:
        raise BadRequestException("CPA and minimum FTD amounts cannot be negative")
    if terms["hold_days"] < 0 or terms["hold_days"] > 180:
        raise BadRequestException("Hold days must be between 0 and 180")
    if deal_type in (DealType.CPA, DealType.HYBRID) and terms["cpa_amount"] <= 0:
        raise BadRequestException("CPA and hybrid deals need a CPA amount")
    if deal_type in (DealType.REVSHARE, DealType.HYBRID) and terms["revshare_rate"] <= 0:
        raise BadRequestException("Revshare and hybrid deals need a revshare rate")
    if deal_type == DealType.TIERED and not terms["tier_table"]:
        raise BadRequestException("Tiered deals need a tier table")
    if deal_type == DealType.TIERED:
        terms["revshare_rate"] = rate(terms["tier_table"][0]["rate"])
    if terms["carryover_cap"] is not None and terms["carryover_cap"] < 0:
        raise BadRequestException("Carryover cap cannot be negative")
    return terms


async def current_deal(db: AsyncSession, partner_id: int, on: Optional[date] = None) -> Optional[AffPartnerDeal]:
    on = on or utcnow().date()
    return (
        await db.execute(
            select(AffPartnerDeal)
            .where(
                AffPartnerDeal.partner_id == partner_id,
                AffPartnerDeal.effective_from <= on,
                or_(AffPartnerDeal.effective_to.is_(None), AffPartnerDeal.effective_to >= on),
            )
            .order_by(AffPartnerDeal.effective_from.desc(), AffPartnerDeal.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def set_deal(
    db: AsyncSession, actor: Actor, partner_id: int, data: Dict[str, Any], effective_from: Optional[date] = None
) -> AffPartnerDeal:
    """Start a new deal from ``effective_from``; the previous one ends the day before. History is kept."""
    await get_partner(db, partner_id)
    plan = await db.get(AffCommissionPlan, int(data["plan_id"])) if data.get("plan_id") else None
    if data.get("plan_id") and plan is None:
        raise NotFoundException("Commission plan not found")
    terms = deal_terms(data, plan)
    start = effective_from or utcnow().date()
    later = (
        await db.execute(select(AffPartnerDeal).where(AffPartnerDeal.partner_id == partner_id, AffPartnerDeal.effective_from >= start))
    ).scalars().all()
    if later:
        raise ConflictException("A deal already starts on or after this date; pick a later effective date")
    previous = await current_deal(db, partner_id, start)
    old = None
    if previous is not None:
        old = _deal_dict(previous)
        previous.effective_to = start - timedelta(days=1)
    deal = AffPartnerDeal(partner_id=partner_id, plan_id=plan.id if plan else None, effective_from=start,
                          created_by=actor.user_id, **terms)
    db.add(deal)
    await db.flush()
    await audit(db, actor, "AFF_DEAL_CHANGED", "aff_partner", partner_id, old=old, new=_deal_dict(deal))
    return deal


def _deal_dict(deal: AffPartnerDeal) -> Dict[str, Any]:
    return {
        "id": deal.id, "deal_type": deal.deal_type.value if hasattr(deal.deal_type, "value") else deal.deal_type,
        "revshare_rate": str(deal.revshare_rate), "cpa_amount": str(deal.cpa_amount), "min_ftd_amount": str(deal.min_ftd_amount),
        "hold_days": deal.hold_days, "carryover": deal.carryover,
        "carryover_cap": None if deal.carryover_cap is None else str(deal.carryover_cap),
        "cpa_geo_list": deal.cpa_geo_list, "tier_table": deal.tier_table,
        "effective_from": str(deal.effective_from), "effective_to": None if deal.effective_to is None else str(deal.effective_to),
    }


deal_dict = _deal_dict


# ---------------------------------------------------------------------------
# Partner creation / lifecycle
# ---------------------------------------------------------------------------


async def _partner_role(db: AsyncSession) -> Role:
    role = (await db.execute(select(Role).where(Role.name == UserRole.PARTNER.value))).scalar_one_or_none()
    if role is None:
        role = Role(name=UserRole.PARTNER.value, description="Affiliate partner")
        db.add(role)
        await db.flush()
    return role


async def create_partner(
    db: AsyncSession,
    actor: Actor,
    *,
    email: str,
    password: Optional[str],
    signup_source: SignupSource,
    status: PartnerStatus,
    profile: Optional[Dict[str, Any]] = None,
    deal: Optional[Dict[str, Any]] = None,
    parent_partner_id: Optional[int] = None,
    manager_id: Optional[str] = None,
    timezone_name: str = "UTC",
    locale: str = "en",
    email_verified: bool = False,
) -> Dict[str, Any]:
    """Create user + partner + profile + wallet + deal + Default source/link atomically.

    Flushes only; the caller commits (so a failure anywhere leaves nothing behind).
    """
    email = email.strip().lower()
    if (await db.execute(select(User.id).where(func.lower(User.email) == email))).first():
        raise ConflictException("An account with this email already exists")
    if parent_partner_id is not None:
        parent = await get_partner(db, parent_partner_id)
        if parent.parent_partner_id is not None and int(await aff_settings.get(db, "subpartner_depth")) <= 1:
            raise BadRequestException("Subpartners cannot invite further subpartners")
        if parent.status != PartnerStatus.ACTIVE:
            raise BadRequestException("The inviting partner is not active")

    role = await _partner_role(db)
    code = await _unique_code(db, AffPartner, AffPartner.partner_code)
    user = User(
        id=str(uuid.uuid4()),
        username=f"p_{code.lower()}",
        email=email,
        full_name=" ".join(filter(None, [(profile or {}).get("first_name"), (profile or {}).get("last_name")])) or None,
        # Admin-created partners without a password must use "forgot password" to set one
        password_hash=hash_password(password) if password else hash_password(uuid.uuid4().hex + uuid.uuid4().hex),
        role_id=role.id,
        is_active=True,
        is_verified=email_verified,
    )
    db.add(user)
    await db.flush()

    sub_rate = Decimal(str(await aff_settings.get(db, "default_subpartner_rate")))
    partner = AffPartner(
        user_id=user.id,
        parent_partner_id=parent_partner_id,
        partner_code=code,
        status=status,
        signup_source=signup_source,
        manager_id=manager_id,
        subpartner_rate=sub_rate,
        timezone=timezone_name or "UTC",
        locale=(locale or "en")[:8],
        approved_at=utcnow() if status == PartnerStatus.ACTIVE else None,
        approved_by=actor.user_id if status == PartnerStatus.ACTIVE else None,
    )
    db.add(partner)
    await db.flush()

    db.add(AffPartnerProfile(partner_id=partner.id, **{k: (profile or {}).get(k) for k in PROFILE_FIELDS}))
    db.add(AffWallet(partner_id=partner.id, currency="USD", available_balance=Decimal("0"),
                     pending_balance=Decimal("0"), reserved_balance=Decimal("0")))

    deal_input = dict(deal or {})
    plan = None
    if deal_input.get("plan_id"):
        plan = await db.get(AffCommissionPlan, int(deal_input["plan_id"]))
        if plan is None:
            raise NotFoundException("Commission plan not found")
    elif not deal_input.get("deal_type"):
        plan = await default_plan(db)
    terms = deal_terms(deal_input, plan)
    db.add(AffPartnerDeal(partner_id=partner.id, plan_id=plan.id if plan else None,
                          effective_from=date(2000, 1, 1), created_by=actor.user_id, **terms))

    source = AffSource(partner_id=partner.id, name="Default", type=SourceType.OTHER, is_default=True)
    db.add(source)
    await db.flush()
    link = AffTrackingLink(partner_id=partner.id, source_id=source.id, link_code=code, name="Default", is_default=True)
    db.add(link)
    await db.flush()

    await audit(db, actor, "AFF_PARTNER_CREATED", "aff_partner", partner.id,
                new={"email": email, "partner_code": code, "status": status.value, "signup_source": signup_source.value,
                     "parent_partner_id": parent_partner_id, "deal": terms})
    return {"user": user, "partner": partner, "source": source, "link": link}


async def set_status(db: AsyncSession, actor: Actor, partner_id: int, status: PartnerStatus, reason: Optional[str] = None) -> AffPartner:
    partner = await get_partner(db, partner_id)
    old = partner.status
    if old == status:
        return partner
    if status == PartnerStatus.ACTIVE and partner.approved_at is None:
        partner.approved_at = utcnow()
        partner.approved_by = actor.user_id
    partner.status = status
    user = await db.get(User, partner.user_id)
    if user is not None:
        user.is_active = status != PartnerStatus.BLOCKED
    await audit(db, actor, "AFF_PARTNER_STATUS", "aff_partner", partner_id, old={"status": old.value}, new={"status": status.value}, reason=reason)
    messages = {
        PartnerStatus.ACTIVE: ("Partner account approved", "Your partner account is active. Your Default tracking link is ready."),
        PartnerStatus.SUSPENDED: ("Partner account suspended", f"Your partner account was suspended. {reason or ''}".strip()),
        PartnerStatus.BLOCKED: ("Partner account blocked", f"Your partner account was blocked. {reason or ''}".strip()),
    }
    if status in messages:
        await notify(db, partner.user_id, *messages[status])
    if status in (PartnerStatus.SUSPENDED, PartnerStatus.BLOCKED):
        # Revoke sessions so the change applies immediately
        from app.repositories.token_repo import TokenRepository

        await TokenRepository(db).revoke_all_for_user(partner.user_id)
    return partner


# ---------------------------------------------------------------------------
# Tracking domains and link URLs
# ---------------------------------------------------------------------------


def _normalise_domain(domain: str) -> str:
    value = domain.strip().lower()
    for prefix in ("https://", "http://"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    value = value.split("/")[0]
    if not value or " " in value or "." not in value and not value.startswith("localhost"):
        raise BadRequestException("Enter a domain like partners.example.com")
    return value


async def active_domains(db: AsyncSession) -> List[AffTrackingDomain]:
    return list(
        (
            await db.execute(
                select(AffTrackingDomain)
                .where(AffTrackingDomain.status == DomainStatus.ACTIVE)
                .order_by(AffTrackingDomain.is_primary.desc(), AffTrackingDomain.id)
            )
        ).scalars().all()
    )


async def link_base(db: AsyncSession) -> str:
    """Base URL of tracking links: the primary active domain, else the configured public URL."""
    domains = await active_domains(db)
    if domains:
        host = domains[0].domain
        scheme = "http" if host.startswith("localhost") or host.startswith("127.") else "https"
        return f"{scheme}://{host}"
    return get_settings().affiliate_public_base_url


async def link_urls(db: AsyncSession, link_code: str, base: Optional[str] = None) -> Dict[str, str]:
    base = base or await link_base(db)
    return {"query": f"{base}/?{urlencode({'ref': link_code})}", "redirect": f"{base}/r/{link_code}"}


async def invite_link(db: AsyncSession, partner: AffPartner) -> str:
    base = await link_base(db)
    return f"{base}/partner/signup?{urlencode({'inviter': partner.partner_code})}"


async def upsert_domain(db: AsyncSession, actor: Actor, domain: str, is_primary: bool, status: DomainStatus,
                        domain_id: Optional[int] = None) -> AffTrackingDomain:
    name = _normalise_domain(domain)
    row = await db.get(AffTrackingDomain, domain_id) if domain_id else None
    if domain_id and row is None:
        raise NotFoundException("Tracking domain not found")
    clash = (await db.execute(select(AffTrackingDomain).where(AffTrackingDomain.domain == name))).scalar_one_or_none()
    if clash is not None and (row is None or clash.id != row.id):
        raise ConflictException("This domain is already registered")
    old = None
    if row is None:
        row = AffTrackingDomain(domain=name, is_primary=is_primary, status=status)
        db.add(row)
    else:
        old = {"domain": row.domain, "is_primary": row.is_primary, "status": row.status.value}
        row.domain, row.is_primary, row.status = name, is_primary, status
    await db.flush()
    if is_primary:
        for other in (await db.execute(select(AffTrackingDomain).where(AffTrackingDomain.id != row.id, AffTrackingDomain.is_primary.is_(True)))).scalars():
            other.is_primary = False
    await db.flush()
    await audit(db, actor, "AFF_DOMAIN_SAVED", "aff_tracking_domain", row.id, old=old,
                new={"domain": name, "is_primary": is_primary, "status": status.value})
    return row


async def check_domain(db: AsyncSession, row: AffTrackingDomain) -> AffTrackingDomain:
    """HTTPS health check: the domain must answer /r/<nonexistent> over TLS."""
    import httpx

    row.last_checked_at = utcnow()
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
            resp = await client.get(f"https://{row.domain}/health")
        row.ssl_ok = True
        row.last_check_error = None if resp.status_code < 500 else f"HTTP {resp.status_code}"
    except httpx.ConnectError as exc:
        row.ssl_ok = False
        row.last_check_error = str(exc)[:255] or "connection failed"
    except Exception as exc:  # TLS errors, timeouts
        row.ssl_ok = False
        row.last_check_error = (type(exc).__name__ + ": " + str(exc))[:255]
    await db.flush()
    return row


# ---------------------------------------------------------------------------
# Sources / campaigns / links / promo codes (partner-owned)
# ---------------------------------------------------------------------------


async def _owned(db: AsyncSession, model: Any, row_id: int, partner_id: Optional[int]) -> Any:
    row = await db.get(model, row_id)
    if row is None or (partner_id is not None and row.partner_id != partner_id):
        raise NotFoundException(f"{model.__name__.replace('Aff', '')} not found")
    return row


async def create_source(db: AsyncSession, actor: Actor, partner_id: int, data: Dict[str, Any]) -> AffSource:
    source = AffSource(partner_id=partner_id, name=data["name"].strip()[:80], type=SourceType(data.get("type") or "OTHER"),
                       url=data.get("url"), description=data.get("description"))
    db.add(source)
    await db.flush()
    await audit(db, actor, "AFF_SOURCE_CREATED", "aff_source", source.id, new={"partner_id": partner_id, "name": source.name})
    return source


async def update_source(db: AsyncSession, actor: Actor, partner_id: Optional[int], source_id: int, data: Dict[str, Any]) -> AffSource:
    source = await _owned(db, AffSource, source_id, partner_id)
    for key in ("name", "url", "description"):
        if data.get(key) is not None:
            setattr(source, key, data[key])
    if data.get("type"):
        source.type = SourceType(data["type"])
    if data.get("status"):
        status = RecordStatus(data["status"])
        if source.is_default and status != RecordStatus.ACTIVE:
            raise BadRequestException("The Default source cannot be archived")
        source.status = status
    await db.flush()
    return source


async def create_campaign(db: AsyncSession, actor: Actor, partner_id: int, data: Dict[str, Any]) -> AffCampaign:
    source = await _owned(db, AffSource, int(data["source_id"]), partner_id)
    code = await _unique_code(db, AffCampaign, AffCampaign.code, 10)
    campaign = AffCampaign(
        partner_id=partner_id, source_id=source.id, name=data["name"].strip()[:80], code=code,
        destination_url=_safe_destination(data.get("destination_url")),
        blocked_countries=sorted({c.strip().upper() for c in data.get("blocked_countries") or [] if c.strip()}) or None,
        start_at=data.get("start_at"), end_at=data.get("end_at"),
    )
    db.add(campaign)
    await db.flush()
    await audit(db, actor, "AFF_CAMPAIGN_CREATED", "aff_campaign", campaign.id, new={"partner_id": partner_id, "name": campaign.name})
    return campaign


async def update_campaign(db: AsyncSession, actor: Actor, partner_id: Optional[int], campaign_id: int, data: Dict[str, Any]) -> AffCampaign:
    campaign = await _owned(db, AffCampaign, campaign_id, partner_id)
    if data.get("name"):
        campaign.name = data["name"].strip()[:80]
    if "destination_url" in data:
        campaign.destination_url = _safe_destination(data.get("destination_url"))
    if "blocked_countries" in data and data["blocked_countries"] is not None:
        campaign.blocked_countries = sorted({c.strip().upper() for c in data["blocked_countries"] if c.strip()}) or None
    for key in ("start_at", "end_at"):
        if key in data:
            setattr(campaign, key, data[key])
    if data.get("status"):
        campaign.status = RecordStatus(data["status"])
    await db.flush()
    await audit(db, actor, "AFF_CAMPAIGN_UPDATED", "aff_campaign", campaign.id, new={k: data[k] for k in data})
    return campaign


def _safe_destination(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if not (url.startswith("https://") or url.startswith("http://")):
        raise BadRequestException("Destination must be an http(s) URL")
    return url[:500]


async def create_link(db: AsyncSession, actor: Actor, partner_id: int, data: Dict[str, Any]) -> AffTrackingLink:
    source = await _owned(db, AffSource, int(data["source_id"]), partner_id)
    campaign_id = None
    if data.get("campaign_id"):
        campaign = await _owned(db, AffCampaign, int(data["campaign_id"]), partner_id)
        if campaign.source_id != source.id:
            raise BadRequestException("The campaign belongs to another source")
        campaign_id = campaign.id
    code = await _unique_code(db, AffTrackingLink, AffTrackingLink.link_code)
    link = AffTrackingLink(partner_id=partner_id, source_id=source.id, campaign_id=campaign_id, link_code=code,
                           name=(data.get("name") or "Link").strip()[:80], destination_url=_safe_destination(data.get("destination_url")))
    db.add(link)
    await db.flush()
    await audit(db, actor, "AFF_LINK_CREATED", "aff_tracking_link", link.id, new={"partner_id": partner_id, "code": code})
    return link


async def update_link(db: AsyncSession, actor: Actor, partner_id: Optional[int], link_id: int, data: Dict[str, Any]) -> AffTrackingLink:
    link = await _owned(db, AffTrackingLink, link_id, partner_id)
    if data.get("name"):
        link.name = data["name"].strip()[:80]
    if "destination_url" in data:
        link.destination_url = _safe_destination(data.get("destination_url"))
    if data.get("status"):
        status = RecordStatus(data["status"])
        if link.is_default and status != RecordStatus.ACTIVE:
            raise BadRequestException("The Default link cannot be paused or archived")
        link.status = status
    await db.flush()
    await audit(db, actor, "AFF_LINK_UPDATED", "aff_tracking_link", link.id, new={k: data[k] for k in data})
    return link


async def create_promo(db: AsyncSession, actor: Actor, partner_id: int, link_id: int, code: Optional[str]) -> AffPromoCode:
    link = await _owned(db, AffTrackingLink, link_id, partner_id)
    if code:
        code = code.strip().upper()
        if not (4 <= len(code) <= 32) or not code.replace("_", "").replace("-", "").isalnum():
            raise BadRequestException("Promo codes are 4-32 letters, digits, - or _")
    else:
        code = await _unique_code(db, AffPromoCode, AffPromoCode.code)
    promo = AffPromoCode(partner_id=partner_id, tracking_link_id=link.id, code=code)
    try:
        async with db.begin_nested():
            db.add(promo)
            await db.flush()
    except IntegrityError as exc:
        raise ConflictException("This promo code is taken") from exc
    await audit(db, actor, "AFF_PROMO_CREATED", "aff_promo_code", promo.id, new={"code": code, "link_id": link.id})
    return promo


async def list_links(db: AsyncSession, partner_ids: Sequence[int]) -> List[AffTrackingLink]:
    return list(
        (
            await db.execute(
                select(AffTrackingLink)
                .where(AffTrackingLink.partner_id.in_(list(partner_ids)))
                .order_by(AffTrackingLink.is_default.desc(), AffTrackingLink.id)
            )
        ).scalars().all()
    )


async def search_partners(
    db: AsyncSession, *, status: Optional[str] = None, q: Optional[str] = None, parent_id: Optional[int] = None,
    has_parent: Optional[bool] = None, limit: int = 50, offset: int = 0,
) -> Dict[str, Any]:
    query = select(AffPartner, User.email).join(User, User.id == AffPartner.user_id)
    filters = []
    if status:
        filters.append(AffPartner.status == PartnerStatus(status))
    if parent_id:
        filters.append(AffPartner.parent_partner_id == parent_id)
    if has_parent is True:
        filters.append(AffPartner.parent_partner_id.is_not(None))
    if q:
        like = f"%{q.strip().lower()}%"
        filters.append(or_(func.lower(User.email).like(like), func.lower(AffPartner.partner_code).like(like)))
    if filters:
        query = query.where(and_(*filters))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await db.execute(query.order_by(AffPartner.id.desc()).limit(limit).offset(offset))).all()
    return {"total": total, "rows": rows}
