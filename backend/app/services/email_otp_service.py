"""One-time email codes for admin two-step verification.

Codes are 6 digits, stored only as a SHA-256 hash in Redis, valid for 10
minutes, single use, invalidated after 5 wrong attempts, and can be re-sent
at most once every 30 seconds.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Optional

from app.core.config import get_settings
from app.core.exceptions import BadRequestException, ForbiddenException, ServiceUnavailableException
from app.core.logging import get_logger
from app.core.redis import get_redis_client
from app.services.email_service import EmailDeliveryError, get_email_service

logger = get_logger("email_otp")

CODE_TTL_SECONDS = 600
RESEND_COOLDOWN_SECONDS = 30
MAX_ATTEMPTS = 5


def mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    visible = name[:2] if len(name) > 2 else name[:1]
    return f"{visible}{'*' * max(3, len(name) - len(visible))}@{domain}"


def ensure_allowed(email: Optional[str]) -> str:
    """Admin codes may only go to addresses listed in ADMIN_OTP_EMAILS (if set)."""
    if not email:
        raise BadRequestException("This account has no email address for verification codes")
    allowed = get_settings().admin_otp_emails
    if allowed and email.strip().lower() not in allowed:
        raise ForbiddenException("This email is not authorised to receive admin verification codes")
    return email.strip().lower()


def _key(purpose: str, user_id: str) -> str:
    return f"2fa:email:{purpose}:{user_id}"


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


async def send_code(user_id: str, email: str, purpose: str) -> dict:
    """Email a fresh code (respecting the resend cooldown). Returns masked target + cooldown."""
    from app.services.email_service import email_delivery_configured

    if get_settings().is_production and not email_delivery_configured():
        raise ServiceUnavailableException(
            "Email sending is not configured on the server (set BREVO_API_KEY and EMAIL_FROM)"
        )
    redis = get_redis_client()
    key = _key(purpose, user_id)
    try:
        if await redis.exists(f"{key}:cooldown"):
            ttl = await redis.ttl(f"{key}:cooldown")
            return {"sent_to": mask_email(email), "resend_in": max(int(ttl), 1), "sent": False}
        code = f"{secrets.randbelow(1_000_000):06d}"
        await redis.set(key, json.dumps({"hash": _hash(code), "email": email, "attempts": 0}), ex=CODE_TTL_SECONDS)
        await redis.set(f"{key}:cooldown", "1", ex=RESEND_COOLDOWN_SECONDS)
    except Exception as exc:
        raise ServiceUnavailableException("Verification service is temporarily unavailable") from exc
    try:
        await get_email_service().send_otp_email(email, code, purpose)
    except EmailDeliveryError as exc:
        logger.error("Verification email failed", error=str(exc))
        await redis.delete(key, f"{key}:cooldown")
        raise ServiceUnavailableException("Could not send the verification email. Try again shortly.") from exc
    logger.info("Verification code emailed", user_id=user_id, purpose=purpose, to=mask_email(email))
    return {"sent_to": mask_email(email), "resend_in": RESEND_COOLDOWN_SECONDS, "sent": True}


async def verify_code(user_id: str, code: str, purpose: str) -> Optional[str]:
    """Check a code; returns the email it was sent to on success (code is then consumed)."""
    redis = get_redis_client()
    key = _key(purpose, user_id)
    try:
        raw = await redis.get(key)
    except Exception as exc:
        raise ServiceUnavailableException("Verification service is temporarily unavailable") from exc
    if not raw:
        return None
    data = json.loads(raw)
    if hmac.compare_digest(data["hash"], _hash(code.strip())):
        await redis.delete(key)
        return data["email"]
    data["attempts"] = int(data.get("attempts", 0)) + 1
    if data["attempts"] >= MAX_ATTEMPTS:
        await redis.delete(key)
    else:
        ttl = await redis.ttl(key)
        await redis.set(key, json.dumps(data), ex=max(int(ttl), 1))
    return None
