"""User profile management service."""

from __future__ import annotations

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user_repo import UserRepository


class UserService:
    """Service handling player profile queries and account updates."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)

    async def get_by_id(self, user_id: str) -> User:
        """Fetch user by ID."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")
        return user

    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> None:
        """Change user password after validating current password."""
        user = await self.get_by_id(user_id)
        if not verify_password(current_password, user.password_hash):
            raise BadRequestException("Current password does not match")

        if len(new_password) < 8:
            raise BadRequestException("New password must be at least 8 characters")

        user.password_hash = hash_password(new_password)
        await self.session.flush()

    async def update_profile(
        self,
        user_id: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
    ) -> User:
        """Update user profile attributes with uniqueness validation."""
        from app.core.exceptions import ConflictException

        user = await self.get_by_id(user_id)
        if username and username != user.username:
            # Changing only the letter case of your own name is allowed
            if username.lower() != user.username.lower() and await self.user_repo.username_exists(username):
                raise ConflictException("Username is already taken")
            user.username = username
        if email and email.lower() != user.email:
            email_lower = email.lower()
            if await self.user_repo.email_exists(email_lower):
                raise ConflictException("Email is already registered")
            user.email = email_lower
        await self.session.flush()
        return user
