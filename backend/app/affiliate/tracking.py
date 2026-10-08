"""Click resolver and attribution.

Click flow (PRD §5): resolve code -> reject inactive link/partner -> bot filter
(UA list, clicks per IP hash per minute) -> insert aff_tracking_clicks with a
click_id -> first-party cookie ``aff_click`` -> redirect to the destination with
click_id appended so the product can send it back in its postbacks.

The redirect never fails because of the database: if the click insert fails
the click is pushed to a Redis backlog that the worker drains later.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate import settings as aff_settings
from app.affiliate.common import risk_event
from app.affiliate.constants import AttributionType, PartnerStatus, RecordStatus, RiskSeverity
from app.affiliate.util import (
    aware,
    click_time,
    hash_ip,
    is_bot_agent,
    new_click_id,
    parse_user_agent,
    utcnow,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.rate_limit import check_rate_limit
from app.models.affiliate import (
    AffCampaign,
    AffPartner,
    AffPromoCode,
    AffTrackingClick,
    AffTrackingLink,
    AffVisitor,
)

logger = get_logger("aff_tracking")

CLICK_COOKIE = "aff_click"
VISITOR_COOKIE = "aff_vid"
BACKLOG_KEY = "aff:click_backlog"
SUB_KEYS = ("sub1", "sub2", "sub3", "sub4", "sub5")


@dataclass
class ClickResult:
    redirect_url: str
    click_id: Optional[str]
    visitor_id: Optional[str]
    cookie_days: int
    tracked: bool
    reason: Optional[str] = None


def _append_query(url: str, params: Dict[str, str]) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in params]
    query.extend((k, v) for k, v in params.items() if v)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


async def _main_site(db: AsyncSession) -> str:
    return get_settings().affiliate_public_base_url


async def default_destination(db: AsyncSession) -> str:
    configured = (await aff_settings.get(db, "default_destination_url") or "").strip()
    return configured or f"{await _main_site(db)}/register"


async def resolve_link(db: AsyncSession, code: str) -> Optional[Tuple[AffTrackingLink, AffPartner, Optional[AffCampaign]]]:
    code = (code or "").strip().upper()
    if not code or len(code) > 24:
        return None
    link = (await db.execute(select(AffTrackingLink).where(AffTrackingLink.link_code == code))).scalar_one_or_none()
    if link is None:
        return None
    partner = await db.get(AffPartner, link.partner_id)
    campaign = await db.get(AffCampaign, link.campaign_id) if link.campaign_id else None
    return link, partner, campaign


async def _visitor(db: AsyncSession, anonymous_id: Optional[str], country: Optional[str], device: str, now: datetime) -> Tuple[Optional[int], str]:
    if not anonymous_id or len(anonymous_id) > 32 or not anonymous_id.isalnum():
        anonymous_id = secrets.token_hex(16)
    row = (await db.execute(select(AffVisitor).where(AffVisitor.anonymous_id == anonymous_id))).scalar_one_or_none()
    if row is None:
        row = AffVisitor(anonymous_id=anonymous_id, first_seen_at=now, last_seen_at=now, country=country, device_type=device)
        db.add(row)
        await db.flush()
    else:
        row.last_seen_at = now
        if country:
            row.country = country
    return row.id, anonymous_id


async def record_click(
    db: AsyncSession,
    code: str,
    *,
    ip: Optional[str],
    user_agent: Optional[str],
    country: Optional[str],
    referrer: Optional[str],
    subs: Dict[str, Optional[str]],
    visitor_cookie: Optional[str] = None,
) -> ClickResult:
    """Resolve a tracking code, log the click and work out where to send the visitor. Commits."""
    cookie_days = int(await aff_settings.get(db, "cookie_days"))
    resolved = await resolve_link(db, code)
    if resolved is None:
        return ClickResult(await _main_site(db), None, None, cookie_days, False, "unknown_code")
    link, partner, campaign = resolved
    now = utcnow()
    if (
        partner is None
        or partner.status != PartnerStatus.ACTIVE
        or link.status != RecordStatus.ACTIVE
        or (campaign is not None and campaign.status != RecordStatus.ACTIVE)
        or (campaign is not None and campaign.end_at is not None and aware(campaign.end_at) < now)
    ):
        return ClickResult(await _main_site(db), None, None, cookie_days, False, "inactive")
    if campaign is not None and country and country in (campaign.blocked_countries or []):
        blocked_url = (await aff_settings.get(db, "blocked_geo_url") or "").strip() or await _main_site(db)
        return ClickResult(blocked_url, None, None, cookie_days, False, "blocked_geo")

    ip_hash = hash_ip(ip)
    device, browser, os_name = parse_user_agent(user_agent)
    is_bot = is_bot_agent(user_agent)
    if not is_bot and ip_hash:
        per_minute = int(await aff_settings.get(db, "bot_clicks_per_minute"))
        allowed = await check_rate_limit(f"aff:clk:{ip_hash}", per_minute, 60)
        if not allowed:
            is_bot = True
            await risk_event(
                db, "CLICK_FLOOD", RiskSeverity.LOW, f"More than {per_minute} clicks per minute from one IP on link {link.link_code}",
                partner_id=partner.id, score=20, meta={"link": link.link_code},
                dedupe_key=f"click-flood:{partner.id}:{now.date()}",
            )
    is_unique = True
    if ip_hash:
        window = int(await aff_settings.get(db, "unique_click_window_hours"))
        seen = (
            await db.execute(
                select(AffTrackingClick.click_id).where(
                    and_(
                        AffTrackingClick.ip_hash == ip_hash,
                        AffTrackingClick.tracking_link_id == link.id,
                        AffTrackingClick.clicked_at >= now - timedelta(hours=window),
                    )
                ).limit(1)
            )
        ).first()
        is_unique = seen is None

    click_id = new_click_id(now)
    clicked_at = click_time(click_id) or now  # ms precision, matches the id
    clean_subs = {k: (subs.get(k) or None) and str(subs[k])[:128] for k in SUB_KEYS}
    row = dict(
        click_id=click_id, clicked_at=clicked_at, tracking_link_id=link.id, partner_id=partner.id,
        source_id=link.source_id, campaign_id=link.campaign_id, ip_hash=ip_hash,
        user_agent=(user_agent or "")[:400] or None, country=country, device_type=device, browser=browser, os=os_name,
        referrer=(referrer or "")[:500] or None, is_bot=is_bot, is_unique=is_unique and not is_bot, **clean_subs,
    )
    anonymous_id = visitor_cookie
    try:
        visitor_id, anonymous_id = await _visitor(db, visitor_cookie, country, device, now)
        db.add(AffTrackingClick(visitor_id=visitor_id, **row))
        await db.commit()
    except Exception as exc:  # never lose the redirect over a slow / failing DB
        await db.rollback()
        logger.warning("Click insert failed, queued to backlog", error=str(exc))
        await _backlog_push(row)

    destination = (
        link.destination_url
        or (campaign.destination_url if campaign else None)
        or await default_destination(db)
    )
    url = _append_query(destination, {"click_id": click_id, "ref": link.link_code})
    return ClickResult(url, click_id, anonymous_id, cookie_days, True)


async def _backlog_push(row: Dict[str, Any]) -> None:
    from app.core.redis import get_redis_client

    payload = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in row.items()}
    try:
        await get_redis_client().rpush(BACKLOG_KEY, json.dumps(payload))
    except Exception as exc:
        logger.error("Click backlog unavailable; click dropped", error=str(exc), click_id=row.get("click_id"))


async def drain_backlog(db: AsyncSession, limit: int = 1000) -> int:
    from app.core.redis import get_redis_client

    redis = get_redis_client()
    done = 0
    for _ in range(limit):
        raw = await redis.lpop(BACKLOG_KEY)
        if raw is None:
            break
        data = json.loads(raw)
        data["clicked_at"] = datetime.fromisoformat(data["clicked_at"])
        exists = (await db.execute(select(AffTrackingClick.click_id).where(AffTrackingClick.click_id == data["click_id"]))).first()
        if not exists:
            db.add(AffTrackingClick(**data))
            done += 1
    await db.commit()
    return done


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


async def find_click(db: AsyncSession, click_id: str) -> Optional[AffTrackingClick]:
    if not click_id or len(click_id) != 26:
        return None
    at = click_time(click_id)
    query = select(AffTrackingClick).where(AffTrackingClick.click_id == click_id.upper())
    if at is not None:  # lets PostgreSQL prune to one monthly partition
        query = query.where(AffTrackingClick.clicked_at.between(at - timedelta(seconds=2), at + timedelta(seconds=2)))
    return (await db.execute(query)).scalar_one_or_none()


@dataclass
class Attribution:
    partner_id: int
    tracking_link_id: Optional[int]
    source_id: Optional[int]
    campaign_id: Optional[int]
    promo_code_id: Optional[int]
    click_id: Optional[str]
    visitor_id: Optional[int]
    attribution_type: AttributionType
    subs: Dict[str, Optional[str]]


async def attribute(
    db: AsyncSession, *, click_id: Optional[str], promo_code: Optional[str], registered_at: datetime
) -> Optional[Attribution]:
    """Default policy: a promo code entered at signup wins; else the last click within the window."""
    if promo_code:
        promo = (
            await db.execute(select(AffPromoCode).where(AffPromoCode.code == promo_code.strip().upper()))
        ).scalar_one_or_none()
        if promo is not None and promo.status == RecordStatus.ACTIVE:
            link = await db.get(AffTrackingLink, promo.tracking_link_id)
            partner = await db.get(AffPartner, promo.partner_id)
            if link is not None and partner is not None and partner.status == PartnerStatus.ACTIVE:
                return Attribution(partner.id, link.id, link.source_id, link.campaign_id, promo.id, None, None,
                                   AttributionType.PROMO, {k: None for k in SUB_KEYS})
    if click_id:
        click = await find_click(db, click_id)
        if click is not None and not click.is_fraud:
            window = int(await aff_settings.get(db, "attribution_window_days"))
            age = aware(registered_at) - aware(click.clicked_at)
            partner = await db.get(AffPartner, click.partner_id)
            if timedelta(0) - timedelta(minutes=5) <= age <= timedelta(days=window) and partner is not None \
                    and partner.status == PartnerStatus.ACTIVE:
                return Attribution(click.partner_id, click.tracking_link_id, click.source_id, click.campaign_id, None,
                                   click.click_id, click.visitor_id, AttributionType.CLICK,
                                   {k: getattr(click, k) for k in SUB_KEYS})
    return None
