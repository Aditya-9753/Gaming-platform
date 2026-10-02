"""Game management and queries service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.game import Game, GameEntry, GameRound
from app.repositories.entry_repo import EntryRepository
from app.repositories.game_repo import GameRepository
from app.repositories.round_repo import RoundRepository


class GameService:
    """Service providing game catalog, active round state, and game history queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.game_repo = GameRepository(session)
        self.round_repo = RoundRepository(session)
        self.entry_repo = EntryRepository(session)

    async def list_games(self) -> List[Game]:
        """List all active games with their settings."""
        return await self.game_repo.list_active()

    async def get_game(self, game_id: str) -> Game:
        """Fetch game metadata by ID."""
        game = await self.game_repo.get_by_id(game_id)
        if not game:
            raise NotFoundException(f"Game '{game_id}' not found")
        return game

    async def get_current_round(self, game_id: str) -> Optional[GameRound]:
        """Fetch currently active or scheduled round for game."""
        await self.get_game(game_id)  # verify existence
        return await self.round_repo.get_active_round(game_id)

    async def get_recent_history(
        self, game_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Fetch recent completed rounds with results and public seeds."""
        await self.get_game(game_id)
        rounds = await self.round_repo.get_recent_completed(game_id, limit=limit)
        return [
            {
                "round_id": r.id,
                "round_no": r.round_no,
                "status": r.status,
                "server_seed_hash": r.server_seed_hash,
                "server_seed": r.server_seed,
                "client_seed": r.client_seed,
                "result": r.result,
                "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            }
            for r in rounds
        ]

    async def list_game_rounds(
        self,
        game_id: str,
        status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[GameRound], int]:
        """Fetch paginated game rounds filtered by game_id, status, and date range."""
        await self.get_game(game_id)
        if from_date and to_date and from_date > to_date:
            raise BadRequestException("from_date must be earlier than or equal to to_date")
        return await self.round_repo.list_rounds(
            game_id=game_id,
            status=status,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
        )

    async def get_game_history_paginated(
        self,
        game_id: str,
        status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Fetch paginated completed rounds history with revealed seeds and outcomes."""
        await self.get_game(game_id)
        if from_date and to_date and from_date > to_date:
            raise BadRequestException("from_date must be earlier than or equal to to_date")
        effective_status: Optional[str | Sequence[str]] = status or [
            "COMPLETED",
            "HISTORY",
        ]
        rounds, total = await self.round_repo.list_rounds(
            game_id=game_id,
            status=effective_status,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
        )
        items = [
            {
                "round_id": r.id,
                "round_no": r.round_no,
                "status": r.status,
                "server_seed_hash": r.server_seed_hash,
                "server_seed": r.server_seed,
                "client_seed": r.client_seed,
                "result": r.result,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            }
            for r in rounds
        ]
        return items, total

    async def get_user_entries(
        self,
        user_id: str,
        game_id: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[GameEntry], int]:
        """Fetch paginated wager history for a user."""
        return await self.entry_repo.get_user_history(
            user_id=user_id,
            game_id=game_id,
            limit=limit,
            offset=offset,
        )
