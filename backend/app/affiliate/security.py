"""Partner sign-up, email verification, terms, account changes, impersonation (partners do not use 2FA)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate import partners as partner_service
from app.affiliate import settings as aff_settings
from app.affiliate.common import Actor, SYSTEM, audit, notify
from app.affiliate.constants import EmailTokenPurpose, PartnerStatus, SignupSource
from app.affiliate.util import hash_ip, sha256, utcnow, aware
from app.core.config import get_settings
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.models.affiliate import AffEmailToken, AffPartner, AffTermsAcceptance, AffTermsVersion
from app.models.user import User
from app.services.email_service import get_email_service

logger = get_logger("aff_security")

# Small built-in list of the most breached passwords (no network call at sign-up)
_BREACHED = {
    "123456789012", "1234567890", "qwertyuiop", "password123", "password1234", "iloveyou123", "1q2w3e4r5t",
    "qwerty12345", "123123123123", "abcdefghij", "passwordpassword", "0987654321", "1111111111", "aaaaaaaaaa",
    "qwerty123456", "letmein1234", "welcome1234", "admin12345", "football123", "princess123", "sunshine123",
    "monkey12345", "dragon12345", "zaq12wsxcde", "1qaz2wsx3edc", "asdfghjkl1", "12345qwert", "qazwsxedc123",
}

_IMPERSONATION_MINUTES = 30


async def times_breached(password: str) -> int:
    """How often the password appears in known breaches (HaveIBeenPwned, k-anonymity).

    Only the first 5 hex characters of the SHA-1 hash leave the server. Returns 0 when the
    service cannot be reached (the local list above still applies).
    """
    import hashlib

    import httpx

    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"https://api.pwnedpasswords.com/range/{prefix}", headers={"Add-Padding": "true"})
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Breached-password check unavailable", error=str(exc))
        return 0
    for line in resp.text.splitlines():
        candidate, _, count = line.partition(":")
        if candidate.strip() == suffix:
            return int(count.strip() or 0)
    return 0


async def check_password(password: str, email: Optional[str] = None) -> None:
    if len(password) < 10:
        raise BadRequestException("Use at least 10 characters")
    if len(password) > 128:
        raise BadRequestException("Use at most 128 characters")
    lowered = password.lower()
    if lowered in _BREACHED or len(set(password)) < 4:
        raise BadRequestException("This password is too common; choose another one")
    if email and email.split("@")[0].lower() in lowered and len(email.split("@")[0]) >= 4:
        raise BadRequestException("The password must not contain your email name")
    if get_settings().AFFILIATE_BREACH_CHECK and await times_breached(password) > 0:
        raise BadRequestException("This password has appeared in a data breach; choose a different one")


# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------


async def latest_terms(db: AsyncSession) -> Optional[AffTermsVersion]:
    return (await db.execute(select(AffTermsVersion).order_by(AffTermsVersion.published_at.desc(), AffTermsVersion.id.desc()).limit(1))).scalar_one_or_none()


async def accept_terms(db: AsyncSession, user_id: str, version_id: int, ip: Optional[str]) -> None:
    exists = (await db.execute(select(AffTermsAcceptance.id).where(
        AffTermsAcceptance.user_id == user_id, AffTermsAcceptance.terms_version_id == version_id))).first()
    if not exists:
        db.add(AffTermsAcceptance(user_id=user_id, terms_version_id=version_id, ip_hash=hash_ip(ip)))
        await db.flush()


async def needs_terms(db: AsyncSession, user_id: str) -> Optional[AffTermsVersion]:
    if not await aff_settings.get(db, "terms_required"):
        return None
    terms = await latest_terms(db)
    if terms is None:
        return None
    accepted = (await db.execute(select(AffTermsAcceptance.id).where(
        AffTermsAcceptance.user_id == user_id, AffTermsAcceptance.terms_version_id == terms.id))).first()
    return None if accepted else terms


# ---------------------------------------------------------------------------
# Sign-up and email verification
# ---------------------------------------------------------------------------


async def _issue_email_token(db: AsyncSession, user_id: str, purpose: EmailTokenPurpose, hours: int) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(AffEmailToken(user_id=user_id, purpose=purpose, token_hash=sha256(raw), expires_at=utcnow() + timedelta(hours=hours)))
    await db.flush()
    return raw


async def send_verification(db: AsyncSession, user: User) -> None:
    raw = await _issue_email_token(db, user.id, EmailTokenPurpose.VERIFY, 48)
    link = f"{get_settings().affiliate_public_base_url}/partner/verify-email?token={raw}"
    try:
        await get_email_service().send(user.email, "Confirm your partner account",
                                       f"Welcome! Confirm your email to activate your partner account:\n\n{link}\n\nThe link is valid for 48 hours.")
    except Exception as exc:  # the account is created either way; the partner can resend
        logger.warning("Verification email failed", error=str(exc))


async def signup(db: AsyncSession, data: Dict[str, Any], ip: Optional[str]) -> Dict[str, Any]:
    email = str(data["email"]).strip().lower()
    await check_password(data["password"], email)
    terms = await latest_terms(db)
    if terms is not None and not data.get("accept_terms"):
        raise BadRequestException("Accept the partner terms to continue")
    if not data.get("confirm_adult"):
        raise BadRequestException("Partners must be adults and must not target minors")
    parent_id = None
    if data.get("inviter"):
        inviter = await partner_service.partner_by_code(db, str(data["inviter"]))
        if inviter is None:
            raise BadRequestException("The invite link is not valid")
        parent_id = inviter.id
    auto = bool(await aff_settings.get(db, "auto_approve_signups"))
    created = await partner_service.create_partner(
        db, SYSTEM, email=email, password=data["password"], signup_source=SignupSource.SELF,
        status=PartnerStatus.ACTIVE if auto else PartnerStatus.PENDING, profile=data.get("profile") or {},
        parent_partner_id=parent_id, timezone_name=data.get("timezone") or "UTC", locale=data.get("locale") or "en",
    )
    if terms is not None:
        await accept_terms(db, created["user"].id, terms.id, ip)
    await send_verification(db, created["user"])
    if parent_id:
        parent = await db.get(AffPartner, parent_id)
        await notify(db, parent.user_id, "New subpartner", f"{email} joined with your invite link.")
    await db.commit()
    return created


async def verify_email(db: AsyncSession, raw_token: str) -> User:
    row = (await db.execute(select(AffEmailToken).where(AffEmailToken.token_hash == sha256(raw_token)))).scalar_one_or_none()
    if row is None or row.purpose != EmailTokenPurpose.VERIFY or row.used_at is not None or aware(row.expires_at) < utcnow():
        raise BadRequestException("This link is invalid or has expired")
    user = await db.get(User, row.user_id)
    if user is None:
        raise NotFoundException("Account not found")
    row.used_at = utcnow()
    user.is_verified = True
    await audit(db, Actor(user_id=user.id, role="PARTNER"), "AFF_EMAIL_VERIFIED", "user", user.id)
    await db.commit()
    return user


# ---------------------------------------------------------------------------
# Account changes
# ---------------------------------------------------------------------------


async def change_password(db: AsyncSession, user: User, current: str, new: str, ip: Optional[str]) -> None:
    if not verify_password(current, user.password_hash):
        raise BadRequestException("The current password is not correct")
    await check_password(new, user.email)
    user.password_hash = hash_password(new)
    from app.repositories.token_repo import TokenRepository

    await TokenRepository(db).revoke_all_for_user(user.id)
    await audit(db, Actor(user_id=user.id, role="PARTNER", ip=ip), "AFF_PASSWORD_CHANGED", "user", user.id)
    await notify(db, user.id, "Password changed", "Your password was changed and other devices were signed out.", "SECURITY")
    await db.commit()


async def change_email(db: AsyncSession, user: User, password: str, new_email: str, ip: Optional[str]) -> None:
    if not verify_password(password, user.password_hash):
        raise BadRequestException("The password is not correct")
    new_email = new_email.strip().lower()
    if (await db.execute(select(User.id).where(User.email == new_email, User.id != user.id))).first():
        raise BadRequestException("This email is already used by another account")
    old = user.email
    user.email = new_email
    user.is_verified = False
    await send_verification(db, user)
    await audit(db, Actor(user_id=user.id, role="PARTNER", ip=ip), "AFF_EMAIL_CHANGED", "user", user.id, old={"email": old}, new={"email": new_email})
    await db.commit()


# ---------------------------------------------------------------------------
# Impersonation (read-only partner view for support)
# ---------------------------------------------------------------------------


async def impersonation_token(db: AsyncSession, actor: Actor, partner_id: int) -> Dict[str, Any]:
    partner = await partner_service.get_partner(db, partner_id)
    user = await db.get(User, partner.user_id)
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=_IMPERSONATION_MINUTES)
    token = jwt.encode(
        {"sub": user.id, "role": "PARTNER", "username": user.username, "imp": actor.user_id, "ro": True,
         "type": "access", "exp": expires},
        settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM,
    )
    await audit(db, actor, "AFF_IMPERSONATION_STARTED", "aff_partner", partner_id, partner_code=partner.partner_code)
    await db.commit()
    return {"access_token": token, "expires_in": _IMPERSONATION_MINUTES * 60, "partner_code": partner.partner_code}

