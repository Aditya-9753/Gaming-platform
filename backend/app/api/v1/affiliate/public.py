"""Public affiliate endpoints: click tracking, partner sign-up, email verification, portal config."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate import security as sec
from app.affiliate import serialize
from app.affiliate import settings as aff_settings
from app.affiliate.constants import PartnerStatus
from app.affiliate.partners import partner_by_code
from app.affiliate.tracking import CLICK_COOKIE, SUB_KEYS, VISITOR_COOKIE, ClickResult, record_click
from app.affiliate.util import client_ip, request_country
from app.core.config import get_settings
from app.core.database import get_db
from app.middleware.rate_limit import rate_limit_dependency
from app.models.affiliate import AffPartner
from app.schemas.affiliate import ClickIn, SignupIn, TokenIn

router = APIRouter(prefix="/aff", tags=["Partner public"])
# Mounted at the site root (outside /api/v1): /r/{code}
redirect_router = APIRouter(tags=["Tracking"])


def _set_cookies(response: Response, result: ClickResult) -> None:
    secure = get_settings().is_production
    if result.click_id:
        response.set_cookie(CLICK_COOKIE, result.click_id, max_age=result.cookie_days * 86400, httponly=True,
                            secure=secure, samesite="lax", path="/")
    if result.visitor_id:
        response.set_cookie(VISITOR_COOKIE, result.visitor_id, max_age=365 * 86400, httponly=True, secure=secure,
                            samesite="lax", path="/")


async def track_redirect(request: Request, code: str, db: AsyncSession) -> RedirectResponse:
    params = request.query_params
    result = await record_click(
        db, code, ip=client_ip(request), user_agent=request.headers.get("user-agent"), country=request_country(request),
        referrer=request.headers.get("referer"), subs={k: params.get(k) for k in SUB_KEYS},
        visitor_cookie=request.cookies.get(VISITOR_COOKIE),
    )
    response = RedirectResponse(result.redirect_url, status_code=302)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    _set_cookies(response, result)
    return response


@redirect_router.get("/r/{code}", include_in_schema=False)
async def redirect_style(code: str, request: Request, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    return await track_redirect(request, code, db)


@router.post("/track/click", dependencies=[Depends(rate_limit_dependency("aff:click", 120, 60))])
async def track_click(body: ClickIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    """Used by the main site when a visitor lands on /?ref=CODE (query-style links)."""
    result = await record_click(
        db, body.ref, ip=client_ip(request), user_agent=request.headers.get("user-agent"), country=request_country(request),
        referrer=body.referrer, subs={k: getattr(body, k) for k in SUB_KEYS}, visitor_cookie=request.cookies.get(VISITOR_COOKIE),
    )
    _set_cookies(response, result)
    return {"tracked": result.tracked, "click_id": result.click_id, "cookie_days": result.cookie_days,
            "redirect_url": result.redirect_url, "reason": result.reason}


@router.get("/public/config")
async def public_config(db: AsyncSession = Depends(get_db)) -> dict:
    config = await aff_settings.get_all(db)
    terms = await sec.latest_terms(db)
    return {**{k: config[k] for k in aff_settings.PUBLIC_KEYS}, "terms": serialize.terms(terms),
            "turnstile_site_key": get_settings().TURNSTILE_SITE_KEY if get_settings().TURNSTILE_SECRET_KEY else None}


@router.get("/public/terms")
async def public_terms(db: AsyncSession = Depends(get_db)) -> dict:
    return {"terms": serialize.terms(await sec.latest_terms(db), with_content=True)}


@router.get("/public/inviter/{code}")
async def inviter(code: str, db: AsyncSession = Depends(get_db)) -> dict:
    partner: Optional[AffPartner] = await partner_by_code(db, code)
    valid = partner is not None and partner.status == PartnerStatus.ACTIVE and partner.parent_partner_id is None
    return {"valid": valid, "partner_code": partner.partner_code if valid else None}


@router.post("/auth/signup", status_code=201, dependencies=[Depends(rate_limit_dependency("aff:signup", 5, 3600))])
async def signup(body: SignupIn, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    created = await sec.signup(db, body.model_dump(), client_ip(request))
    partner = created["partner"]
    return {"partner_code": partner.partner_code, "status": partner.status.value, "verification_sent": True}


@router.post("/auth/verify-email", dependencies=[Depends(rate_limit_dependency("aff:verify", 20, 3600))])
async def verify_email(body: TokenIn, db: AsyncSession = Depends(get_db)) -> dict:
    user = await sec.verify_email(db, body.token)
    partner = (await db.execute(select(AffPartner).where(AffPartner.user_id == user.id))).scalar_one_or_none()
    return {"verified": True, "status": partner.status.value if partner else None}
