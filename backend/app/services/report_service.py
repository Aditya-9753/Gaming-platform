"""Platform financial and gaming reporting service."""

from __future__ import annotations

from typing import Any, Dict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import GameEntry, GameRound
from app.models.user import User


class ReportService:
    """Service providing aggregate metrics, GGR, and activity statistics."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_platform_overview(self) -> Dict[str, Any]:
        """Compute key platform metrics: total wagers, total payouts, GGR, user count."""
        # 1. Total users
        user_count_stmt = select(func.count(User.id))
        user_count = (await self.session.execute(user_count_stmt)).scalar_one() or 0

        # 2. Total bets & payouts
        financials_stmt = select(
            func.count(GameEntry.id),
            func.sum(GameEntry.bet_amount),
            func.sum(GameEntry.payout_amount),
        )
        fin_res = await self.session.execute(financials_stmt)
        total_entries, total_wagered, total_payouts = fin_res.one()

        total_wagered = total_wagered or 0
        total_payouts = total_payouts or 0
        ggr = total_wagered - total_payouts

        # 3. Total completed rounds
        rounds_stmt = select(func.count(GameRound.id)).where(GameRound.status == "COMPLETED")
        rounds_completed = (await self.session.execute(rounds_stmt)).scalar_one() or 0

        return {
            "total_users": user_count,
            "total_wagers_count": total_entries or 0,
            "total_wagered_paise": total_wagered,
            "total_payouts_paise": total_payouts,
            "ggr_paise": ggr,
            "completed_rounds": rounds_completed,
        }
