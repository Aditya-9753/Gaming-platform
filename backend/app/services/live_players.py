"""How many real people are playing each lobby game right now.

Counts distinct player accounts (role USER) that placed a bet in the game in
the last few minutes. Simulated bot accounts and staff are never counted, so
the lobby shows exactly what the super admin sees as real activity.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import UserRole
from app.games.simulated_players import BOT_NAMES
from app.models.game import GameEntry, GameRound
from app.models.role import Role
from app.models.user import User

WINDOW_MINUTES = 5
_CACHE_SECONDS = 15
_cache: Dict[str, object] = {}

# Lobby tile id -> backend game ids
LOBBY_GAMES = ("aviator", "color", "mines", "teen_patti")


def lobby_id(game_id: str) -> str | None:
    if game_id == "color" or game_id.startswith("wingo"):
        return "color"
    return game_id if game_id in LOBBY_GAMES else None


async def live_player_counts(db: AsyncSession) -> Dict[str, object]:
    now = time.monotonic()
    if _cache and now - float(_cache["at"]) < _CACHE_SECONDS:  # type: ignore[arg-type]
        return _cache["data"]  # type: ignore[return-value]
    since = datetime.now(timezone.utc) - timedelta(minutes=WINDOW_MINUTES)
    rows = (await db.execute(
        select(GameRound.game_id, GameEntry.user_id)
        .join(GameRound, GameRound.id == GameEntry.round_id)
        .join(User, User.id == GameEntry.user_id)
        .join(Role, Role.id == User.role_id)
        .where(
            GameEntry.created_at >= since,
            Role.name == UserRole.USER.value,
            User.username.notin_(BOT_NAMES),
        )
        .group_by(GameRound.game_id, GameEntry.user_id)
    )).all()
    players: Dict[str, set] = {g: set() for g in LOBBY_GAMES}
    for game_id, user_id in rows:
        key = lobby_id(game_id)
        if key:
            players[key].add(user_id)
    data = {
        "window_minutes": WINDOW_MINUTES,
        "games": {g: len(ids) for g, ids in players.items()},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _cache.update(at=now, data=data)
    return data


def reset_cache() -> None:
    _cache.clear()


__all__ = ["live_player_counts", "lobby_id", "reset_cache", "WINDOW_MINUTES", "LOBBY_GAMES"]
