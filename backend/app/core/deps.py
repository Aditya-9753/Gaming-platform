"""FastAPI dependency injection — get_current_user and require_permission."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set

from fastapi import Cookie, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import PermissionCode, UserRole
from app.core.database import get_db
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.logging import get_logger
from app.core.permissions import check_role_permission
from app.core.redis import get_redis
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.user_repo import UserRepository

logger = get_logger("deps")
_bearer = HTTPBearer(auto_error=False)


class CurrentUser:
    """Thin wrapper returned by get_current_user dependency."""

    def __init__(self, user: User, permissions: Set[str]) -> None:
        self.id = user.id
        self.username = user.username
        self.email = user.email
        self.role = user.role.name if user.role else UserRole.USER.value
        self.is_active = user.is_active
        self.is_verified = user.is_verified
        self.totp_enabled = user.totp_enabled
        self.two_factor_method = user.two_factor_method
        self.full_name = user.full_name
        self.permissions = permissions
        self.role_id = user.role_id
        self.created_at = user.created_at
        self._user = user  # raw ORM object if needed downstream


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Validate Bearer JWT, load user + permissions from DB.

    Raises UnauthorizedException if token is missing/invalid/expired.
    """
    token: Optional[str] = None

    if credentials:
        token = credentials.credentials
    else:
        # Fallback: try Authorization header manually (for test clients)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise UnauthorizedException("Authentication required")

    try:
        payload = decode_access_token(token)
    except JWTError:
        raise UnauthorizedException("Invalid or expired access token")

    if payload.get("type") != "access":
        raise UnauthorizedException("Wrong token type")

    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise UnauthorizedException("Malformed token payload")

    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise UnauthorizedException("User not found")
    if not user.is_active:
        raise ForbiddenException("Account suspended")

    if (
        get_settings().admin_2fa_required
        and user.role
        and user.role.name.upper() in (UserRole.ADMIN.value, UserRole.SUPERADMIN.value)
        and not user.totp_enabled
    ):
        allowed_setup_paths = {
            "/api/v1/auth/me",
            "/api/v1/auth/totp/setup",
            "/api/v1/auth/totp/verify",
            "/api/v1/auth/2fa/email/send",
            "/api/v1/auth/2fa/email/verify",
        }
        if request.url.path not in allowed_setup_paths:
            raise ForbiddenException(
                "Administrator access is restricted until authenticator setup is complete"
            )

    # Collect granted permission codes from the role
    granted: Set[str] = set()
    if user.role:
        for perm in user.role.permissions:
            granted.add(perm.code)

    return CurrentUser(user, granted)


async def get_optional_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Optional[CurrentUser]:
    """Like get_current_user but returns None instead of raising when no token."""
    try:
        return await get_current_user(request, credentials, db)
    except (UnauthorizedException, ForbiddenException):
        return None


def require_permission(*codes: PermissionCode) -> Callable:
    """FastAPI dependency factory enforcing one or more permission codes.

    SUPERADMIN always passes. All other roles must have every listed code.

    Usage::

        @router.get("/admin/users")
        async def list_users(
            current_user: CurrentUser = Depends(require_permission(PermissionCode.USER_READ)),
        ):
            ...
    """

    async def _check(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        require_2fa = get_settings().admin_2fa_required
        if current_user.role == UserRole.SUPERADMIN.value:
            if require_2fa and not current_user.totp_enabled:
                raise ForbiddenException("Two-factor authentication is required for super-admin access")
            return current_user

        if (
            require_2fa
            and current_user.role == UserRole.ADMIN.value
            and not current_user.totp_enabled
        ):
            raise ForbiddenException("Two-factor authentication is required for admin access")
        if PermissionCode.ROLE_MANAGE in codes:
            raise ForbiddenException("Role and administrator management is super-admin only")

        for code in codes:
            if not check_role_permission(current_user.role, current_user.permissions, code):
                raise ForbiddenException(
                    f"Permission denied: {code.value} is required"
                )
        return current_user

    return _check
