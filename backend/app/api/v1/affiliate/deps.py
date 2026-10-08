"""Dependencies for partner endpoints: the partner always comes from the token, never the body."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate.common import Actor, actor_from
from app.affiliate.constants import PartnerStatus
from app.affiliate.partners import partner_for_user
from app.affiliate.security import needs_terms
from app.affiliate.util import client_ip
from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import AppException, ForbiddenException
from app.models.affiliate import AffPartner
from app.models.user import User


class PartnerStateException(AppException):
    """403 with a machine-readable reason so the portal can show the right screen."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message=message, status_code=403, error_code=code)


@dataclass
class PartnerCtx:
    partner: AffPartner
    user: User
    actor: Actor
    ip: Optional[str]
    impersonated_by: Optional[str]


async def partner_ctx(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PartnerCtx:
    if current_user.role.upper() != "PARTNER":
        raise ForbiddenException("This area is for partners")
    partner = await partner_for_user(db, current_user.id)
    if partner is None:
        raise ForbiddenException("No partner account is linked to this login")
    ip = client_ip(request)
    return PartnerCtx(partner, current_user._user, actor_from(current_user, ip), ip, current_user.impersonated_by)


async def active_partner(ctx: PartnerCtx = Depends(partner_ctx), db: AsyncSession = Depends(get_db)) -> PartnerCtx:
    """Approved, verified partner who accepted the current terms."""
    if not ctx.user.is_verified and not ctx.impersonated_by:
        raise PartnerStateException("Confirm your email address first", "PARTNER_EMAIL_UNVERIFIED")
    if ctx.partner.status == PartnerStatus.PENDING:
        raise PartnerStateException("Your partner account is waiting for approval", "PARTNER_PENDING")
    if ctx.partner.status in (PartnerStatus.SUSPENDED, PartnerStatus.BLOCKED):
        raise PartnerStateException(f"Your partner account is {ctx.partner.status.value.lower()}", "PARTNER_SUSPENDED")
    if not ctx.impersonated_by and await needs_terms(db, ctx.user.id) is not None:
        raise PartnerStateException("Accept the updated partner terms", "PARTNER_TERMS_REQUIRED")
    return ctx
