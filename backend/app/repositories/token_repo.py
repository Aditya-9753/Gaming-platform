"""Refresh-token repository.

Handles the rotate-on-use / reuse-detection family model:
- Every token stores its SHA-256 hash (never plaintext).
- Each token belongs to a *family* (uuid). On rotation a sibling is
  created in the same family; the old one is revoked.
- If a *revoked* token is presented, every token in that family is
  immediately revoked (stolen token detection / refresh-token reuse).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken


class TokenRepository:
    """Data-access layer for RefreshToken."""

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_by_hash(self, token_hash: str) -> Optional[RefreshToken]:
        result = await self._db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_active_family(self, family_id: str) -> Sequence[RefreshToken]:
        """Return all non-revoked tokens in a family (for reuse detection)."""
        result = await self._db.execute(
            select(RefreshToken).where(
                RefreshToken.family_id == family_id,
                RefreshToken.revoked.is_(False),
            )
        )
        return result.scalars().all()

    async def count_active_for_user(self, user_id: str) -> int:
        from sqlalchemy import func
        result = await self._db.execute(
            select(func.count()).select_from(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
            )
        )
        return result.scalar_one()

    # ------------------------------------------------------------------
    # Writes (caller handles commit / rollback)
    # ------------------------------------------------------------------

    async def create(self, token: RefreshToken) -> RefreshToken:
        self._db.add(token)
        await self._db.flush()
        return token

    async def revoke(self, token: RefreshToken) -> None:
        token.revoked = True
        self._db.add(token)
        await self._db.flush()

    async def revoke_family(self, family_id: str) -> int:
        """Revoke every token in the family. Returns count of rows affected."""
        result = await self._db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id)
            .values(revoked=True)
            .execution_options(synchronize_session="fetch")
        )
        await self._db.flush()
        return result.rowcount

    async def revoke_all_for_user(self, user_id: str) -> int:
        """Logout-everywhere: revoke all tokens for a user."""
        result = await self._db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
            .values(revoked=True)
            .execution_options(synchronize_session="fetch")
        )
        await self._db.flush()
        return result.rowcount
