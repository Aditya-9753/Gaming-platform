"""Mines engine stub for background maintenance and session monitoring."""

from __future__ import annotations

import asyncio
from typing import Optional
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.games.base.engine import BaseGameEngine


class MinesEngine(BaseGameEngine):
    """Mines engine providing maintenance loop for abandoned solo sessions."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis,
    ) -> None:
        super().__init__(
            game_id="mines",
            session_factory=session_factory,
            redis=redis,
        )

    async def run_round_cycle(self) -> None:
        """Solo games run on-demand per player; background cycle handles housekeeping."""
        await asyncio.sleep(60.0)
