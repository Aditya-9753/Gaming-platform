"""Step-up verification for sensitive payment actions.

An admin who already signed in proves possession of their second factor
again (authenticator code, or a code emailed for this purpose) and receives a
short-lived step-up token. Money-moving admin endpoints require that token in
the ``X-Step-Up-Token`` header. The token is a JWT of its own type and
audience, so it can never be used as an access token (and vice versa).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import status
from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.exceptions import AppException, BadRequestException, ForbiddenException
from app.services import email_otp_service
from app.services.two_factor_service import two_factor_service

STEP_UP_TTL_SECONDS = 300
_AUDIENCE = "payments-step-up"
_TYPE = "step_up"
OTP_PURPOSE = "payment"


class StepUpRequiredException(AppException):
    def __init__(self, message: str = "Confirm this action with your verification code") -> None:
        super().__init__(message=message, status_code=status.HTTP_403_FORBIDDEN, error_code="STEP_UP_REQUIRED")


def _issue(user_id: str, method: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user_id,
        "type": _TYPE,
        "aud": _AUDIENCE,
        "mfa": method,
        "iat": int(now.timestamp()),
        "exp": now + timedelta(seconds=STEP_UP_TTL_SECONDS),
    }
    return jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


async def send_email_code(user) -> dict:
    if not (user.totp_enabled and user.two_factor_method == "email"):
        raise BadRequestException("Your account uses an authenticator app — enter its 6-digit code instead")
    email = email_otp_service.ensure_allowed(user.email)
    return await email_otp_service.send_code(user.id, email, OTP_PURPOSE)


async def verify_and_issue(user, code: str) -> dict:
    """Check the second factor and return {token, expires_in, method}."""
    if not user.totp_enabled:
        raise BadRequestException("Set up two-step verification first (Admin → Email 2FA)")
    if user.two_factor_method == "email":
        if not await email_otp_service.verify_code(user.id, code, OTP_PURPOSE):
            raise ForbiddenException("Invalid or expired verification code")
        method = "email"
    else:
        if not two_factor_service.verify_code(user.totp_secret or "", code):
            raise ForbiddenException("Invalid authenticator code")
        method = "totp"
    return {"token": _issue(user.id, method), "expires_in": STEP_UP_TTL_SECONDS, "method": method}


def require(current_user, token: Optional[str]) -> str:
    """Return the MFA method used, or raise StepUpRequiredException.

    Accounts without 2FA can only exist where admin 2FA is not enforced
    (local development); they pass with method "none".
    """
    if not current_user.totp_enabled:
        if get_settings().admin_2fa_required:
            raise ForbiddenException("Two-factor authentication is required for payment actions")
        return "none"
    if not token:
        raise StepUpRequiredException()
    settings = get_settings()
    try:
        claims = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM], audience=_AUDIENCE)
    except JWTError:
        raise StepUpRequiredException("Verification expired — enter a fresh code")
    if claims.get("type") != _TYPE or claims.get("sub") != current_user.id:
        raise StepUpRequiredException()
    return str(claims.get("mfa") or "unknown")
