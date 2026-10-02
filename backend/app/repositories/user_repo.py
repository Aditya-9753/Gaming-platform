"""User repository: all DB queries touching the users table."""

from __future__ import annotations

from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.role import Role
from app.models.user import User


class UserRepository:
    """Data-access layer for User model. No business logic lives here."""

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_by_id(self, user_id: str) -> Optional[User]:
        """Return user by primary key, eagerly loading role and role.permissions."""
        result = await self._db.execute(
            select(User)
            .options(selectinload(User.role).selectinload(Role.permissions))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        """Return user by email address (case-insensitive)."""
        result = await self._db.execute(
            select(User)
            .options(selectinload(User.role).selectinload(Role.permissions))
            .where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[User]:
        """Return user by username."""
        result = await self._db.execute(
            select(User)
            .options(selectinload(User.role).selectinload(Role.permissions))
            .where(func.lower(User.username) == username.lower())
        )
        return result.scalars().first()

    async def email_exists(self, email: str) -> bool:
        result = await self._db.execute(
            select(User.id).where(User.email == email.lower())
        )
        return result.scalar_one_or_none() is not None

    async def username_exists(self, username: str) -> bool:
        result = await self._db.execute(
            select(User.id).where(func.lower(User.username) == username.lower())
        )
        return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------------
    # Writes (caller is responsible for commit / rollback)
    # ------------------------------------------------------------------

    async def create(self, user: User) -> User:
        """Persist a new User row (flush but do not commit)."""
        self._db.add(user)
        await self._db.flush()
        await self._db.refresh(user)
        return user

    async def save(self, user: User) -> User:
        """Merge changes for an existing user (flush but do not commit)."""
        self._db.add(user)
        await self._db.flush()
        await self._db.refresh(user)
        return user
