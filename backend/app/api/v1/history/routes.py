"""Gameplay and bet history routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.game_service import GameService

router = APIRouter(prefix="/history", tags=["History"])

from app.games.fairness_guard import public_selection as _public_selection


@router.get("/bets")
async def get_my_bet_history(
    game_id: Optional[str] = Query(None, description="Optional game filter (aviator, color, mines, cricket)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve paginated wager history for the authenticated user."""
    svc = GameService(db)
    offset = (page - 1) * page_size
    entries, total = await svc.get_user_entries(
        user_id=current_user.id,
        game_id=game_id,
        limit=page_size,
        offset=offset,
    )

    items = [
        {
            "entry_id": e.id,
            "round_id": e.round_id,
            "game_id": e.round.game_id if e.round else None,
            "round_no": e.round.round_no if e.round else None,
            "bet_amount": e.bet_amount,
            "payout_amount": e.payout_amount,
            "multiplier": (e.multiplier / 100.0) if e.multiplier else None,
            "status": e.status,
            "selection": _public_selection(e.selection, e.status),
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }
