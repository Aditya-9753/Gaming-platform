"""Leaderboard public query API routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_optional_current_user
from app.services.leaderboard_service import LeaderboardService

router = APIRouter(prefix="/leaderboard", tags=["Leaderboard"])


@router.get("")
async def get_leaderboard(
    period: str = Query("DAILY", description="DAILY, WEEKLY, ALL_TIME"),
    game_id: Optional[str] = Query(None, description="Optional specific game ID"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    viewer: Optional[CurrentUser] = Depends(get_optional_current_user),
) -> List[Dict[str, Any]]:
    """Top rankings for the timeframe. Public: names are masked (usernames can be mobile numbers),
    no user ids; ``is_me`` marks the signed-in viewer's own row."""
    from app.utils.validators import mask_username

    svc = LeaderboardService(db)
    rows = await svc.get_leaderboard(period=period, game_id=game_id, limit=limit)
    viewer_id = viewer.id if viewer else None
    return [{**{k: v for k, v in row.items() if k != "user_id"}, "username": mask_username(row["username"]),
             "is_me": viewer_id is not None and row["user_id"] == viewer_id} for row in rows]


@router.get("/recent-wins")
async def recent_wins(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Latest winning bets across all games (player names masked)."""
    from sqlalchemy import select

    from app.models.game import GameEntry, GameRound
    from app.models.user import User
    from app.utils.validators import mask_username

    rows = await db.execute(
        select(GameEntry, User.username, GameRound.game_id)
        .join(User, User.id == GameEntry.user_id)
        .join(GameRound, GameRound.id == GameEntry.round_id)
        .where(GameEntry.status == "WON", GameEntry.payout_amount > 0)
        .order_by(GameEntry.updated_at.desc())
        .limit(limit)
    )
    return [
        {
            "player": mask_username(username),
            "game_id": game_id,
            "bet_amount": entry.bet_amount,
            "payout_amount": entry.payout_amount,
            "multiplier": (entry.multiplier / 100.0) if entry.multiplier else None,
            "won_at": entry.updated_at.isoformat() if entry.updated_at else None,
        }
        for entry, username, game_id in rows.all()
    ]
