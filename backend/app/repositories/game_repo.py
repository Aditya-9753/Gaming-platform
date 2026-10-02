"""Repository for games and game settings data access."""

from __future__ import annotations

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.game import Game, GameSetting


class GameRepository:
    """Repository handling Game and GameSetting database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, game_id: str) -> Optional[Game]:
        """Fetch game by ID with settings preloaded."""
        stmt = (
            select(Game)
            .where(Game.id == game_id)
            .options(selectinload(Game.settings))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(self) -> List[Game]:
        """List all active games ordered by name."""
        stmt = (
            select(Game)
            .where(Game.is_active == True)  # noqa: E712
            .options(selectinload(Game.settings))
            .order_by(Game.name.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self) -> List[Game]:
        """List all games (including inactive)."""
        stmt = (
            select(Game)
            .options(selectinload(Game.settings))
            .order_by(Game.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_settings(self, game_id: str) -> Optional[GameSetting]:
        """Fetch settings for a specific game."""
        stmt = select(GameSetting).where(GameSetting.game_id == game_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_settings(
        self,
        game_id: str,
        min_bet: Optional[int] = None,
        max_bet: Optional[int] = None,
        house_edge_percent: Optional[int] = None,
        config: Optional[dict] = None,
    ) -> Optional[GameSetting]:
        """Update game configuration and limits."""
        settings = await self.get_settings(game_id)
        if not settings:
            return None

        if min_bet is not None:
            settings.min_bet = min_bet
        if max_bet is not None:
            settings.max_bet = max_bet
        if house_edge_percent is not None:
            settings.house_edge_percent = house_edge_percent
        if config is not None:
            settings.config = config

        await self.session.flush()
        return settings
