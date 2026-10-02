"""Leaderboard aggregation and ranking service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.game import GameEntry
from app.models.leaderboard import Leaderboard


class LeaderboardService:
    """Service computing and serving platform leaderboards."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def refresh_leaderboard(
        self,
        period: str = "DAILY",
        game_id: Optional[str] = None,
        limit: int = 50,
    ) -> int:
        """Aggregate gameplay metrics and update the leaderboards table."""
        period_upper = period.upper()
        now = datetime.now(timezone.utc)

        if period_upper == "DAILY":
            period_start = now - timedelta(days=1)
        elif period_upper == "WEEKLY":
            period_start = now - timedelta(days=7)
        elif period_upper in ("ALL_TIME", "ALLTIME", "MONTHLY"):
            period_start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        else:
            period_start = now - timedelta(days=1)

        stmt = (
            select(
                GameEntry.user_id,
                func.sum(GameEntry.bet_amount).label("wagered"),
                func.sum(GameEntry.payout_amount).label("won"),
            )
            .where(
                GameEntry.created_at >= period_start,
                GameEntry.status.in_(["WON", "LOST", "COMPLETED", "SETTLED"]),
            )
        )

        if game_id:
            from app.models.game import GameRound
            stmt = stmt.join(GameRound, GameEntry.round_id == GameRound.id).where(GameRound.game_id == game_id)

        stmt = stmt.group_by(GameEntry.user_id).order_by(desc("won")).limit(limit)
        res = await self.session.execute(stmt)
        rows = res.all()

        # Delete existing entries for this period and game
        del_stmt = select(Leaderboard).where(Leaderboard.period == period_upper)
        if game_id:
            del_stmt = del_stmt.where(Leaderboard.game_id == game_id)
        else:
            del_stmt = del_stmt.where(Leaderboard.game_id.is_(None))
        old_entries = (await self.session.execute(del_stmt)).scalars().all()
        for old in old_entries:
            await self.session.delete(old)
        await self.session.flush()

        rank = 1
        for user_id, wagered, won in rows:
            wagered_val = int(wagered or 0)
            won_val = int(won or 0)
            lb = Leaderboard(
                user_id=user_id,
                game_id=game_id,
                period=period_upper,
                total_wagered=wagered_val,
                total_won=won_val,
                net_profit=won_val - wagered_val,
                rank=rank,
                period_start=period_start,
                period_end=now,
            )
            self.session.add(lb)
            rank += 1

        await self.session.commit()
        return len(rows)

    async def get_leaderboard(
        self,
        period: str = "DAILY",
        game_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve cached leaderboard rankings."""
        period_upper = period.upper()
        stmt = (
            select(Leaderboard)
            .options(selectinload(Leaderboard.user))
            .where(Leaderboard.period == period_upper)
        )

        if game_id:
            stmt = stmt.where(Leaderboard.game_id == game_id)
        else:
            stmt = stmt.where(Leaderboard.game_id.is_(None))

        stmt = stmt.order_by(Leaderboard.rank).limit(limit)
        res = await self.session.execute(stmt)
        entries = res.scalars().all()

        return [
            {
                "rank": e.rank,
                "user_id": e.user_id,
                "username": e.user.username if e.user else f"Player_{e.user_id[:6]}",
                "period": e.period,
                "total_wagered": e.total_wagered,
                "total_won": e.total_won,
                "net_profit": e.net_profit,
                "period_start": e.period_start.isoformat(),
                "period_end": e.period_end.isoformat(),
            }
            for e in entries
        ]
