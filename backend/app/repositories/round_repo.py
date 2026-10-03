"""Repository for game rounds and game round results data access."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import GameRoundLifecycle, RoundStatus
from app.models.game import GameResult, GameRound


class RoundRepository:
    """Repository handling GameRound and GameResult database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_round(
        self,
        game_id: str,
        round_no: int,
        server_seed_hash: str,
        server_seed: Optional[str] = None,
        client_seed: Optional[str] = None,
        status: str = RoundStatus.SCHEDULED.value,
        started_at: Optional[datetime] = None,
    ) -> GameRound:
        """Create a new game round with cryptographic commitment."""
        game_round = GameRound(
            game_id=game_id,
            round_no=round_no,
            server_seed_hash=server_seed_hash,
            server_seed=server_seed,
            client_seed=client_seed,
            status=status,
            started_at=started_at,
        )
        self.session.add(game_round)
        await self.session.flush()
        return game_round

    async def get_by_id(self, round_id: str) -> Optional[GameRound]:
        """Fetch game round by its unique UUID ID."""
        stmt = (
            select(GameRound)
            .where(GameRound.id == round_id)
            .options(selectinload(GameRound.game_result))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_game_and_round_no(
        self, game_id: str, round_no: int
    ) -> Optional[GameRound]:
        """Fetch specific round number for a game."""
        stmt = (
            select(GameRound)
            .where(GameRound.game_id == game_id, GameRound.round_no == round_no)
            .options(selectinload(GameRound.game_result))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_round(self, game_id: str) -> Optional[GameRound]:
        """Fetch the most recently created round for a game."""
        stmt = (
            select(GameRound)
            .where(GameRound.game_id == game_id)
            .order_by(desc(GameRound.round_no))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_round(self, game_id: str) -> Optional[GameRound]:
        """Fetch the currently active round (SCHEDULED, BETTING, or RUNNING)."""
        active_statuses = [
            RoundStatus.SCHEDULED.value,
            GameRoundLifecycle.WAITING.value,
            RoundStatus.BETTING.value,
            GameRoundLifecycle.BETTING_OPEN.value,
            GameRoundLifecycle.CREATED.value,
            GameRoundLifecycle.OPEN.value,
            GameRoundLifecycle.LOCKED.value,
            RoundStatus.RUNNING.value,
            GameRoundLifecycle.CRASHED.value,
            GameRoundLifecycle.SETTLING.value,
            GameRoundLifecycle.RESULT.value,
            GameRoundLifecycle.SETTLED.value,
        ]
        stmt = (
            select(GameRound)
            .where(GameRound.game_id == game_id, GameRound.status.in_(active_statuses))
            .order_by(desc(GameRound.round_no))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_recent_completed(
        self, game_id: str, limit: int = 20
    ) -> List[GameRound]:
        """Fetch recent completed rounds with results (for history/trends)."""
        stmt = (
            select(GameRound)
            .where(
                GameRound.game_id == game_id,
                GameRound.status.in_(
                    [RoundStatus.COMPLETED.value, GameRoundLifecycle.HISTORY.value]
                ),
            )
            .options(selectinload(GameRound.game_result))
            .order_by(desc(GameRound.round_no))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        round_id: str,
        status: str,
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
    ) -> Optional[GameRound]:
        """Update round status and timing markers."""
        game_round = await self.get_by_id(round_id)
        if not game_round:
            return None

        game_round.status = status
        if started_at is not None:
            game_round.started_at = started_at
        if ended_at is not None:
            game_round.ended_at = ended_at

        await self.session.flush()
        return game_round

    async def complete_round(
        self,
        round_id: str,
        server_seed: str,
        result_payload: Dict[str, Any],
        ended_at: Optional[datetime] = None,
    ) -> Optional[GameRound]:
        """Mark round completed, reveal server seed, and attach outcome."""
        game_round = await self.get_by_id(round_id)
        if not game_round:
            return None

        game_round.status = RoundStatus.COMPLETED.value
        game_round.server_seed = server_seed
        game_round.result = result_payload
        game_round.ended_at = ended_at or datetime.now(timezone.utc)

        await self.session.flush()
        return game_round

    async def save_round_result(
        self,
        round_id: str,
        outcome: Dict[str, Any],
        total_bets: int,
        total_payouts: int,
    ) -> GameResult:
        """Create or update aggregated game result row."""
        stmt = select(GameResult).where(GameResult.round_id == round_id)
        existing = (await self.session.execute(stmt)).scalar_one_or_none()

        if existing:
            existing.outcome = outcome
            existing.total_bets = total_bets
            existing.total_payouts = total_payouts
            await self.session.flush()
            return existing

        res = GameResult(
            round_id=round_id,
            outcome=outcome,
            total_bets=total_bets,
            total_payouts=total_payouts,
        )
        self.session.add(res)
        await self.session.flush()
        return res

    async def list_rounds(
        self,
        game_id: Optional[str] = None,
        status: Optional[str | Sequence[str]] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
        newest_first: bool = False,
    ) -> Tuple[List[GameRound], int]:
        """Fetch paginated game rounds filtered by game, status, and date range.

        ``newest_first`` orders by creation time, which is the only meaningful
        order when several games (each with its own round numbering) are mixed.
        """
        stmt = select(GameRound).options(selectinload(GameRound.game_result))
        count_stmt = select(func.count(GameRound.id))

        filters = []
        if game_id:
            filters.append(GameRound.game_id == game_id)
        if isinstance(status, str):
            filters.append(GameRound.status == status)
        elif status:
            filters.append(GameRound.status.in_(status))
        if from_date:
            filters.append(GameRound.created_at >= from_date)
        if to_date:
            filters.append(GameRound.created_at <= to_date)
        if from_date and to_date and from_date > to_date:
            from app.core.exceptions import BadRequestException

            raise BadRequestException("from_date must be earlier than or equal to to_date")

        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        order = (desc(GameRound.created_at),) if newest_first else (desc(GameRound.round_no), desc(GameRound.created_at))
        stmt = stmt.order_by(*order).limit(limit).offset(offset)
        rounds_res = await self.session.execute(stmt)
        return list(rounds_res.scalars().all()), total
