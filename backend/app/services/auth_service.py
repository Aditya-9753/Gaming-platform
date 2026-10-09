"""Auth service: register, login, refresh, logout, password-reset.

Non-negotiable rules enforced here:
- Virtual-credits only; signup bonus goes through ONE transaction via
  WalletRepository so balance_before / balance_after / idempotency_key
  are all recorded.
- Refresh tokens: rotate on every use, store only SHA-256 hash, detect
  re-use of a revoked token → revoke entire family.
- Passwords: Argon2id via app.core.security.
- No random; secrets module only (generate_secure_random_token).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import MFA_REQUIRED_ROLES, TransactionStatus, TransactionType, UserRole
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    generate_secure_random_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.role import Role
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.repositories.wallet_repo import WalletRepository
from app.services.email_service import get_email_service
from app.services.two_factor_service import two_factor_service
from sqlalchemy import select

logger = get_logger("auth_service")
settings = get_settings()

# Redis key helpers
_PWD_RESET_PREFIX = "pwd_reset:"
_PWD_RESET_TTL = 3600  # 1 hour


class AuthService:
    """Orchestrates authentication business logic.

    Depends on repositories for DB I/O; never runs raw queries.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._db = session
        self._users = UserRepository(session)
        self._tokens = TokenRepository(session)
        self._wallets = WalletRepository(session)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register(
        self,
        username: str,
        email: Optional[str],
        password: str,
        age_confirmed: bool,
        click_id: Optional[str] = None,
        promo_code: Optional[str] = None,
        country: Optional[str] = None,
    ) -> Tuple[User, str, str]:
        """Create user + wallet + signup bonus in a single DB transaction.

        Returns (user, raw_access_token, raw_refresh_token).
        """
        if not age_confirmed:
            raise BadRequestException("Age confirmation is required")

        email = email.strip().lower() if email else None
        if email and await self._users.email_exists(email):
            raise ConflictException("Email address is already registered")
        if await self._users.username_exists(username):
            raise ConflictException("Username is already taken")

        # Resolve USER role
        role_result = await self._db.execute(
            select(Role).where(Role.name == UserRole.USER.value)
        )
        user_role = role_result.scalar_one_or_none()
        if not user_role:
            raise BadRequestException("Platform not yet initialised — run seed_db.py first")

        user = User(
            id=str(uuid.uuid4()),
            username=username,
            email=email,
            password_hash=hash_password(password),
            role_id=user_role.id,
            is_active=True,
            is_verified=False,
        )
        user = await self._users.create(user)

        # Signup bonus (atomic; single transaction, ledger row with idempotency_key)
        from app.services import platform_settings

        bonus_paise = (await platform_settings.get_all(self._db)).get(
            "signup_bonus_paise", settings.INITIAL_FAUCET_CREDITS
        )
        wallet = Wallet(
            id=str(uuid.uuid4()),
            user_id=user.id,
            balance=bonus_paise,
            locked_balance=0,
            currency="VIRTUAL",
        )
        wallet = await self._wallets.create(wallet)

        tx = WalletTransaction(
            id=str(uuid.uuid4()),
            wallet_id=wallet.id,
            idempotency_key=f"signup-bonus-{user.id}",
            type=TransactionType.FAUCET.value,
            amount=bonus_paise,
            balance_before=0,
            balance_after=bonus_paise,
            status=TransactionStatus.COMPLETED.value,
            description="Signup welcome bonus",
            reference="SIGNUP",
        )
        await self._wallets.add_transaction(tx)

        # Referred player: report to the affiliate platform in the same transaction (outbox)
        from app.affiliate import operator_bridge

        await operator_bridge.player_registered(
            self._db, user.id, click_id=click_id, promo_code=promo_code, country=country
        )

        # Issue tokens
        family_id = str(uuid.uuid4())
        access_token, refresh_raw = await self._issue_token_pair(user, family_id)

        await self._db.commit()
        logger.info("New user registered", user_id=user.id, username=username)
        return user, access_token, refresh_raw

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(
        self,
        identifier: str,
        password: str,
        totp_code: Optional[str] = None,
    ) -> Tuple[User, str, str]:
        """Verify credentials and return (user, access_token, raw_refresh_token).

        ``identifier`` is a username or an email address.
        """
        identifier = identifier.strip()
        if "@" in identifier:
            user = await self._users.get_by_email(identifier.lower())
        else:
            user = await self._users.get_by_username(identifier)

        if not user or not verify_password(password, user.password_hash):
            raise UnauthorizedException("Invalid username or password")

        if not user.is_active:
            raise ForbiddenException("This account has been suspended")

        # The development seed passwords are public (they are in the repository): in production
        # an account still using one must set a new password before it can sign in
        if settings.is_production:
            from app.core.bootstrap import DEFAULT_ACCOUNTS

            if password in {account["password"] for account in DEFAULT_ACCOUNTS}:
                logger.warning("Sign-in with a default password blocked", user_id=user.id)
                raise ForbiddenException("This account uses a default password. Use 'Forgot password' to set a new one.")

        # Admin 2FA enforcement: Admin users MUST provide a valid TOTP code
        role_name = user.role.name.upper() if user.role else ""
        is_admin_user = role_name in MFA_REQUIRED_ROLES

        if is_admin_user:
            if user.totp_enabled and user.two_factor_method == "email":
                await self._email_second_factor(user, totp_code)
            elif user.totp_enabled:
                if not totp_code:
                    raise UnauthorizedException(
                        "Authenticator code required for this administrator account"
                    )
                if not two_factor_service.verify_code(user.totp_secret or "", totp_code):
                    raise UnauthorizedException("Invalid authenticator code")
        elif user.totp_enabled:
            if not totp_code:
                raise UnauthorizedException("TOTP code required")
            if not two_factor_service.verify_code(user.totp_secret or "", totp_code):
                raise UnauthorizedException("Invalid TOTP code")

        user.last_login_at = datetime.now(timezone.utc)
        await self._users.save(user)

        family_id = str(uuid.uuid4())
        access_token, refresh_raw = await self._issue_token_pair(user, family_id)

        await self._db.commit()
        logger.info("User logged in", user_id=user.id)
        return user, access_token, refresh_raw

    # ------------------------------------------------------------------
    # Token Refresh  (rotate on every use, detect reuse)
    # ------------------------------------------------------------------

    async def refresh(self, raw_refresh_token: str) -> Tuple[str, str]:
        """Rotate refresh token; revoke family if old/revoked token is reused.

        Returns (new_access_token, new_raw_refresh_token).
        """
        token_hash = hash_token(raw_refresh_token)
        stored = await self._tokens.get_by_hash(token_hash)

        if not stored:
            raise UnauthorizedException("Invalid refresh token")

        if stored.revoked:
            # Stolen-token detection: revoke the entire family
            await self._tokens.revoke_family(stored.family_id)
            await self._db.commit()
            logger.warning(
                "Refresh token reuse detected — family revoked",
                family_id=stored.family_id,
                user_id=stored.user_id,
            )
            raise UnauthorizedException(
                "Refresh token already used. All sessions have been revoked."
            )

        if stored.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            await self._tokens.revoke(stored)
            await self._db.commit()
            raise UnauthorizedException("Refresh token has expired")

        user = await self._users.get_by_id(stored.user_id)
        if not user or not user.is_active:
            raise ForbiddenException("Account is inactive")

        # Revoke old token, issue new sibling in same family
        await self._tokens.revoke(stored)
        access_token, new_refresh_raw = await self._issue_token_pair(
            user, stored.family_id
        )

        await self._db.commit()
        return access_token, new_refresh_raw

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    async def logout(self, raw_refresh_token: str) -> None:
        """Revoke the current refresh token (single device logout)."""
        token_hash = hash_token(raw_refresh_token)
        stored = await self._tokens.get_by_hash(token_hash)
        if stored and not stored.revoked:
            await self._tokens.revoke(stored)
            await self._db.commit()

    async def logout_all(self, user_id: str) -> None:
        """Revoke every refresh token for the user (logout from all devices)."""
        await self._tokens.revoke_all_for_user(user_id)
        await self._db.commit()

    # ------------------------------------------------------------------
    # Forgot / Reset Password
    # ------------------------------------------------------------------

    async def forgot_password(self, email: str) -> None:
        """Send password-reset email (always returns 200 to prevent enumeration)."""
        user = await self._users.get_by_email(email.lower())
        if not user:
            return  # silent — don't reveal whether address is registered

        raw_token = generate_secure_random_token(32)
        token_hash = hash_token(raw_token)

        # Store token hash in Redis with 1h TTL
        from app.core.redis import get_redis_client
        redis = get_redis_client()
        key = f"{_PWD_RESET_PREFIX}{token_hash}"
        try:
            await redis.set(key, user.id, ex=_PWD_RESET_TTL)
        except Exception:
            logger.warning("Redis unavailable — cannot store password-reset token")
            return

        email_svc = get_email_service()
        await email_svc.send_password_reset_email(user.email, raw_token)
        logger.info("Password reset email sent", user_id=user.id)

    async def reset_password(self, raw_token: str, new_password: str) -> None:
        """Validate reset token, update password hash, and revoke all sessions."""
        token_hash = hash_token(raw_token)
        key = f"{_PWD_RESET_PREFIX}{token_hash}"

        from app.core.redis import get_redis_client
        redis = get_redis_client()
        try:
            user_id_bytes = await redis.get(key)
            user_id = user_id_bytes if isinstance(user_id_bytes, str) else (user_id_bytes.decode() if user_id_bytes else None)
        except Exception:
            raise BadRequestException("Password reset service temporarily unavailable")

        if not user_id:
            raise BadRequestException("Invalid or expired reset token")

        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")

        user.password_hash = hash_password(new_password)
        await self._users.save(user)

        # Revoke all sessions for security
        await self._tokens.revoke_all_for_user(user.id)

        # Delete reset token from Redis
        try:
            await redis.delete(key)
        except Exception:
            pass

        await self._db.commit()
        logger.info("Password reset successful", user_id=user.id)

    # ------------------------------------------------------------------
    # Email one-time codes (2FA) for admins
    # ------------------------------------------------------------------

    async def _email_second_factor(self, user: User, code: Optional[str]) -> None:
        from app.core.exceptions import SecondFactorRequiredException
        from app.services import email_otp_service as otp

        email = otp.ensure_allowed(user.email)
        if not code:
            info = await otp.send_code(user.id, email, "login")
            raise SecondFactorRequiredException(
                f"Verification code sent to {info['sent_to']}. Enter it to sign in.",
                details={"method": "email", **info},
            )
        if not await otp.verify_code(user.id, code, "login"):
            raise UnauthorizedException("Invalid or expired verification code")

    async def email_2fa_send(self, user_id: str, email: Optional[str]) -> dict:
        from app.services import email_otp_service as otp

        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")
        target = otp.ensure_allowed(email or user.email)
        if target != (user.email or "").lower():
            owner = await self._users.get_by_email(target)
            if owner and owner.id != user.id:
                raise ConflictException("That email belongs to another account")
        return await otp.send_code(user.id, target, "setup")

    async def email_2fa_verify(self, user_id: str, code: str) -> str:
        from app.services import email_otp_service as otp

        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")
        email = await otp.verify_code(user.id, code, "setup")
        if not email:
            raise UnauthorizedException("Invalid or expired verification code")
        user.email = email
        user.totp_enabled = True
        user.totp_secret = None
        user.two_factor_method = "email"
        await self._users.save(user)
        await self._db.commit()
        return email

    # ------------------------------------------------------------------
    # TOTP (2FA) for admins
    # ------------------------------------------------------------------

    async def totp_setup(self, user_id: str) -> Tuple[str, str]:
        """Generate a new TOTP secret for the user (not yet activated).

        Returns (secret, provisioning_uri).
        """
        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")

        secret = two_factor_service.generate_secret()
        user.totp_secret = secret
        # totp_enabled stays False until they verify the first code
        await self._users.save(user)
        await self._db.commit()

        uri = two_factor_service.get_provisioning_uri(secret, user.username)
        return secret, uri

    async def totp_verify_and_enable(self, user_id: str, code: str) -> None:
        """Verify a TOTP code and mark 2FA as enabled."""
        user = await self._users.get_by_id(user_id)
        if not user or not user.totp_secret:
            raise BadRequestException("TOTP not set up — call /auth/totp/setup first")

        if not two_factor_service.verify_code(user.totp_secret, code):
            raise UnauthorizedException("Invalid TOTP code")

        user.totp_enabled = True
        user.two_factor_method = "totp"
        await self._users.save(user)
        await self._db.commit()

    async def totp_disable(self, user_id: str, code: str) -> None:
        """Disable TOTP after verifying the last valid code."""
        user = await self._users.get_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")

        if user.totp_enabled:
            if not two_factor_service.verify_code(user.totp_secret or "", code):
                raise UnauthorizedException("Invalid TOTP code")

        user.totp_enabled = False
        user.totp_secret = None
        await self._users.save(user)
        await self._db.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _issue_token_pair(
        self, user: User, family_id: str
    ) -> Tuple[str, str]:
        """Create an access JWT and a new refresh token DB row.

        Returns (access_token, raw_refresh_token). The raw token is
        delivered to the client; only its SHA-256 hash is stored.
        """
        role_name = user.role.name if user.role else UserRole.USER.value

        access_token = create_access_token(
            {"sub": user.id, "role": role_name, "username": user.username}
        )

        raw_refresh = generate_secure_random_token(48)
        refresh_hash = hash_token(raw_refresh)
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

        rt = RefreshToken(
            id=str(uuid.uuid4()),
            user_id=user.id,
            family_id=family_id,
            token_hash=refresh_hash,
            expires_at=expires_at,
            revoked=False,
        )
        await self._tokens.create(rt)
        return access_token, raw_refresh
