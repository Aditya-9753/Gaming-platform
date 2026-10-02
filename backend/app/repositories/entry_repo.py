"""Repository for player game entries and bets."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.game import GameEntry, GameRound


class EntryRepository:
    """Repository handling GameEntry database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_entry(
        self,
        round_id: str,
        user_id: str,
        bet_amount: int,
        idempotency_key: str,
        selection: Optional[Dict[str, Any]] = None,
        multiplier: Optional[int] = None,
        payout_amount: int = 0,
        status: str = "PLACED",
    ) -> GameEntry:
        """Create a new game wager entry."""
        entry = GameEntry(
            round_id=round_id,
            user_id=user_id,
            bet_amount=bet_amount,
            idempotency_key=idempotency_key,
            selection=selection,
            multiplier=multiplier,
            payout_amount=payout_amount,
            status=status,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_by_id(self, entry_id: str) -> Optional[GameEntry]:
        """Fetch entry by ID."""
        stmt = (
            select(GameEntry)
            .where(GameEntry.id == entry_id)
            .options(selectinload(GameEntry.round))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, entry_id: str) -> Optional[GameEntry]:
        """Fetch an entry under a row lock before changing its settlement state."""
        stmt = select(GameEntry).where(GameEntry.id == entry_id).with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, idempotency_key: str) -> Optional[GameEntry]:
        """Fetch entry by unique idempotency key."""
        stmt = select(GameEntry).where(GameEntry.idempotency_key == idempotency_key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_round_id(self, round_id: str) -> List[GameEntry]:
        """Fetch all entries placed in a given round."""
        stmt = (
            select(GameEntry)
            .where(GameEntry.round_id == round_id)
            .order_by(GameEntry.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_user_round_entries(
        self, round_id: str, user_id: str
    ) -> List[GameEntry]:
        """Fetch a specific user's entries for a round."""
        stmt = (
            select(GameEntry)
            .where(GameEntry.round_id == round_id, GameEntry.user_id == user_id)
            .order_by(GameEntry.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_user_active_entry(
        self, round_id: str, user_id: str
    ) -> Optional[GameEntry]:
        """Fetch a user's active/placed entry in an unsettled round."""
        stmt = (
            select(GameEntry)
            .where(
                GameEntry.round_id == round_id,
                GameEntry.user_id == user_id,
                GameEntry.status == "PLACED",
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_history(
        self,
        user_id: str,
        game_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[GameEntry], int]:
        """Get paginated history of entries for a user."""
        stmt = select(GameEntry).join(GameRound, GameEntry.round_id == GameRound.id)
        count_stmt = select(func.count(GameEntry.id)).join(
            GameRound, GameEntry.round_id == GameRound.id
        )

        filters = [GameEntry.user_id == user_id]
        if game_id:
            filters.append(GameRound.game_id == game_id)

        stmt = stmt.where(*filters).options(selectinload(GameEntry.round))
        count_stmt = count_stmt.where(*filters)

        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        stmt = stmt.order_by(desc(GameEntry.created_at)).limit(limit).offset(offset)
        entries_res = await self.session.execute(stmt)
        entries = list(entries_res.scalars().all())

        return entries, total

    async def update_settlement(
        self,
        entry_id: str,
        status: str,
        payout_amount: int,
        multiplier: Optional[int] = None,
    ) -> Optional[GameEntry]:
        """Update entry with outcome and payout."""
        entry = await self.get_by_id(entry_id)
        if not entry:
            return None

        entry.status = status
        entry.payout_amount = payout_amount
        if multiplier is not None:
            entry.multiplier = multiplier

        await self.session.flush()
        return entry
