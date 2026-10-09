"""Authentication API router — all /api/v1/auth/* endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ip import of_request as client_ip_of
from app.core.config import get_settings
from app.core.constants import MFA_REQUIRED_ROLES, PermissionCode
from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from pydantic import BaseModel, EmailStr, Field

from app.core.exceptions import BadRequestException, SecondFactorRequiredException, UnauthorizedException
from app.core.rate_limit import (
    failed_login_count,
    is_locked_out,
    record_failed_login,
    reset_failed_attempts,
)
from app.services import captcha_service
from app.middleware.rate_limit import rate_limit_dependency
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TOTPSetupResponse,
    TOTPVerifyRequest,
    TokenResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])
settings = get_settings()

# Cookie config
_COOKIE_NAME = "refresh_token"
_COOKIE_SECURE = settings.is_production
_COOKIE_SAMESITE = "none" if settings.is_production else "lax"


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_COOKIE_NAME,
        path="/api/v1/auth",
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
    )


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=201,
    dependencies=[
        Depends(rate_limit_dependency("auth:register", max_requests=5, window_seconds=300))
    ],
)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Register a new player account.

    Creates user, virtual-credit wallet and signup-bonus ledger entry in one transaction.
    Returns access JWT in body; refresh token in httpOnly cookie.
    """
    svc = AuthService(db)
    from app.affiliate.util import request_country

    _user, access_token, refresh_raw = await svc.register(
        username=body.username,
        email=body.email,
        password=body.password,
        age_confirmed=body.age_confirmed,
        click_id=body.click_id or request.cookies.get("aff_click"),
        promo_code=body.promo_code,
        country=request_country(request),
    )
    _set_refresh_cookie(response, refresh_raw)
    return TokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/username-available")
async def username_available(
    username: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Live check used by the sign-up form (usernames are unique, case-insensitive)."""
    import re

    from app.repositories.user_repo import UserRepository

    candidate = username.strip()
    if len(candidate) < 3:
        return {"username": candidate, "available": False, "reason": "Too short: use at least 3 characters", "suggestions": []}
    if len(candidate) > 50:
        return {"username": candidate, "available": False, "reason": "Too long: use at most 50 characters", "suggestions": []}
    if not re.fullmatch(r"[A-Za-z0-9_]+", candidate):
        return {"username": candidate, "available": False,
                "reason": "Only letters, numbers and _ are allowed (no spaces or symbols)", "suggestions": []}
    repo = UserRepository(db)
    if not await repo.username_exists(candidate):
        return {"username": candidate, "available": True, "reason": None, "suggestions": []}

    # Offer a few free alternatives built from the same name
    import secrets

    base = candidate[:44]
    pool = [f"{base}_{n}" for n in (1, 7, 11, 99)] + [f"{base}{secrets.randbelow(900) + 100}" for _ in range(4)]
    suggestions = []
    for option in pool:
        if option not in suggestions and not await repo.username_exists(option):
            suggestions.append(option)
        if len(suggestions) == 3:
            break
    return {"username": candidate, "available": False, "reason": "This username is already taken", "suggestions": suggestions}


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[
        Depends(rate_limit_dependency("auth:login", max_requests=10, window_seconds=60))
    ],
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate with username (or email) + password (+ optional TOTP code).

    Tracks failed attempts per identifier+IP and locks out after 5 consecutive failures.
    """
    client_ip = client_ip_of(request)
    identifier = body.identifier.lower()

    # Lockout check
    locked, remaining = await is_locked_out(identifier, client_ip)
    if locked:
        raise BadRequestException(
            f"Account is temporarily locked. Try again in {remaining} seconds."
        )

    captcha_on = captcha_service.enabled()
    if captcha_on and await failed_login_count(identifier, client_ip) >= captcha_service.CAPTCHA_AFTER:
        if not await captcha_service.verify(body.captcha_token, client_ip):
            raise captcha_service.CaptchaRequiredException()

    svc = AuthService(db)
    try:
        _user, access_token, refresh_raw = await svc.login(
            identifier=body.identifier,
            password=body.password,
            totp_code=body.totp_code,
        )
    except SecondFactorRequiredException:
        raise  # correct password, code just emailed: not a failed attempt
    except Exception:
        attempts = await record_failed_login(
            identifier, client_ip, lock_after=captcha_service.LOCK_AFTER if captcha_on else captcha_service.CAPTCHA_AFTER
        )
        if captcha_on and attempts >= captcha_service.CAPTCHA_AFTER and attempts < captcha_service.LOCK_AFTER:
            raise captcha_service.CaptchaRequiredException("Email or password incorrect. Complete the captcha to try again")
        raise

    # Success — clear any lockout counter
    await reset_failed_attempts(identifier, client_ip)
    _set_refresh_cookie(response, refresh_raw)
    return TokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> Response | TokenResponse:
    """Rotate refresh token.

    Reads the token from the httpOnly cookie set during login/register.
    Issues a new access + refresh pair; old refresh token is revoked.
    If a revoked token is presented, the entire token family is revoked
    (re-use / theft detection).
    """
    raw_token: Optional[str] = request.cookies.get(_COOKIE_NAME)
    if not raw_token:
        return Response(status_code=204)

    svc = AuthService(db)
    new_access, new_refresh_raw = await svc.refresh(raw_token)
    _set_refresh_cookie(response, new_refresh_raw)
    return TokenResponse(
        access_token=new_access,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke the current refresh token and clear the cookie."""
    raw_token: Optional[str] = request.cookies.get(_COOKIE_NAME)
    if raw_token:
        svc = AuthService(db)
        await svc.logout(raw_token)
    _clear_refresh_cookie(response)


# ---------------------------------------------------------------------------
# POST /auth/logout-all
# ---------------------------------------------------------------------------

@router.post("/logout-all", status_code=204)
async def logout_all(
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke every refresh token for this user (all devices)."""
    svc = AuthService(db)
    await svc.logout_all(current_user.id)
    _clear_refresh_cookie(response)


# ---------------------------------------------------------------------------
# POST /auth/forgot-password
# ---------------------------------------------------------------------------

@router.post(
    "/forgot-password",
    status_code=204,
    dependencies=[
        Depends(rate_limit_dependency("auth:forgot", max_requests=3, window_seconds=300))
    ],
)
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Send a password-reset email. Always 204 to prevent email enumeration."""
    svc = AuthService(db)
    await svc.forgot_password(body.email)


# ---------------------------------------------------------------------------
# POST /auth/reset-password
# ---------------------------------------------------------------------------

@router.post(
    "/reset-password",
    status_code=204,
    dependencies=[
        Depends(rate_limit_dependency("auth:reset", max_requests=5, window_seconds=300))
    ],
)
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Consume a reset token and change the user's password."""
    svc = AuthService(db)
    await svc.reset_password(body.token, body.new_password)


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

@router.get("/me", response_model=MeResponse)
async def me(
    current_user: CurrentUser = Depends(get_current_user),
) -> MeResponse:
    """Return the authenticated user's profile."""
    return MeResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        totp_enabled=current_user.totp_enabled,
        two_factor_method=current_user.two_factor_method if current_user.totp_enabled else None,
        full_name=current_user.full_name,
        is_staff=current_user.role.upper() not in ("USER", "PARTNER"),
        permissions=sorted(
            {code.value for code in PermissionCode}
            if current_user.role.upper() == "SUPERADMIN"
            else current_user.permissions
        ),
        requires_2fa_setup=(
            settings.admin_2fa_required
            and current_user.role.upper() in MFA_REQUIRED_ROLES
            and not current_user.totp_enabled
        ),
    )


# ---------------------------------------------------------------------------
# TOTP / 2FA  (admin-focused)
# ---------------------------------------------------------------------------

class EmailSecondFactorSend(BaseModel):
    email: Optional[EmailStr] = None


class EmailSecondFactorVerify(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


@router.post("/2fa/email/send")
async def email_2fa_send(
    body: EmailSecondFactorSend,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Email a 6-digit code to set up email two-step verification."""
    return await AuthService(db).email_2fa_send(current_user.id, str(body.email) if body.email else None)


@router.post("/2fa/email/verify")
async def email_2fa_verify(
    body: EmailSecondFactorVerify,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Confirm the emailed code; from now on every sign-in emails a fresh code."""
    email = await AuthService(db).email_2fa_verify(current_user.id, body.code)
    return {"enabled": True, "method": "email", "email": email}


@router.post("/totp/setup", response_model=TOTPSetupResponse)
async def totp_setup(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TOTPSetupResponse:
    """Generate a TOTP secret. Scan the QR code, then verify with /totp/verify."""
    svc = AuthService(db)
    secret, uri = await svc.totp_setup(current_user.id)
    return TOTPSetupResponse(secret=secret, provisioning_uri=uri)


@router.post("/totp/verify", status_code=204)
async def totp_verify(
    body: TOTPVerifyRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Confirm the TOTP code is working and enable 2FA on the account."""
    svc = AuthService(db)
    await svc.totp_verify_and_enable(current_user.id, body.code)


@router.delete("/totp/disable", status_code=204)
async def totp_disable(
    body: TOTPVerifyRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Disable TOTP — requires a valid code from the current authenticator."""
    svc = AuthService(db)
    await svc.totp_disable(current_user.id, body.code)


@router.post("/ws-ticket")
async def get_websocket_ticket(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Issue short-lived single-use ticket for WebSocket authentication."""
    from app.core.redis import get_redis_client
    from app.websocket.auth import create_ws_ticket

    redis = get_redis_client()
    ticket = await create_ws_ticket(redis, current_user.id, ttl_seconds=60)
    return {"ticket": ticket, "expires_in": 60, "user_id": current_user.id}
