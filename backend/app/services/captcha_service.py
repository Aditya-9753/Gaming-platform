"""Cloudflare Turnstile verification (sign-in captcha after repeated failures)."""

from __future__ import annotations

from typing import Optional

from fastapi import status

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging import get_logger

logger = get_logger("captcha")

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
CAPTCHA_AFTER = 5   # failed attempts before a captcha is required
LOCK_AFTER = 10     # failed attempts before the 15-minute lock


class CaptchaRequiredException(AppException):
    def __init__(self, message: str = "Complete the captcha to continue") -> None:
        super().__init__(message=message, status_code=status.HTTP_403_FORBIDDEN, error_code="CAPTCHA_REQUIRED",
                         details={"site_key": get_settings().TURNSTILE_SITE_KEY})


def enabled() -> bool:
    settings = get_settings()
    return bool(settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET_KEY)


async def verify(token: Optional[str], ip: Optional[str]) -> bool:
    if not token:
        return False
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(VERIFY_URL, data={"secret": get_settings().TURNSTILE_SECRET_KEY, "response": token,
                                                        "remoteip": ip or ""})
            return bool(resp.json().get("success"))
    except Exception as exc:  # the captcha service being down must not let attackers through
        logger.warning("Turnstile verification failed", error=str(exc))
        return False
