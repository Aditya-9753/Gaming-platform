"""Public client-seed rotation for provably-fair rounds.

Each round's outcome is HMAC-SHA256(serverSeed, "clientSeed:nonce"). The
server seed is new and secret per round; the client seed is public. A super
admin can rotate the platform client seed: every round created afterwards
uses the new value (a player's own client seed, e.g. in Mines, still wins).
Rotation changes no outcome that already exists and is fully audit logged,
and every past value stays listed so old rounds remain verifiable.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import SystemSetting

ACTIVE_KEY = "fairness.client_seed"
HISTORY_KEY = "fairness.client_seed_history"
HISTORY_LIMIT = 50


async def _get_json(db: AsyncSession, key: str) -> Any:
    row = await db.get(SystemSetting, key)
    if row is None:
        return None
    try:
        return json.loads(row.value)
    except (TypeError, ValueError):
        return None


async def _set_json(db: AsyncSession, key: str, value: Any, description: str, actor_id: Optional[str]) -> None:
    row = await db.get(SystemSetting, key)
    if row is None:
        db.add(SystemSetting(key=key, value=json.dumps(value), description=description, updated_by_id=actor_id))
    else:
        row.value = json.dumps(value)
        row.updated_by_id = actor_id


async def active_client_seed(db: AsyncSession) -> Optional[str]:
    data = await _get_json(db, ACTIVE_KEY)
    return (data or {}).get("seed") or None


async def seed_state(db: AsyncSession) -> Dict[str, Any]:
    active = await _get_json(db, ACTIVE_KEY)
    history: List[Dict[str, Any]] = await _get_json(db, HISTORY_KEY) or []
    return {
        "active": active,
        "default_rule": "When no platform seed is set, each round uses its own round id as the client seed.",
        "history": history,
    }


def _validate(seed: str) -> str:
    seed = seed.strip()
    if not 8 <= len(seed) <= 64 or not all(c.isalnum() or c in "-_" for c in seed):
        raise ValueError("Client seed must be 8-64 letters, numbers, - or _")
    return seed


async def rotate(db: AsyncSession, actor_id: Optional[str], actor_name: str, custom_seed: Optional[str] = None) -> Dict[str, Any]:
    seed = _validate(custom_seed) if custom_seed else secrets.token_hex(16)
    now = datetime.now(timezone.utc).isoformat()
    previous = await _get_json(db, ACTIVE_KEY)
    history: List[Dict[str, Any]] = await _get_json(db, HISTORY_KEY) or []
    if previous and previous.get("seed"):
        history.insert(0, {**previous, "retired_at": now})
    entry = {"seed": seed, "activated_at": now, "by": actor_name}
    await _set_json(db, ACTIVE_KEY, entry, "Public client seed for new provably-fair rounds", actor_id)
    await _set_json(db, HISTORY_KEY, history[:HISTORY_LIMIT], "Retired public client seeds", actor_id)
    return {"active": entry, "previous": previous}


__all__ = ["active_client_seed", "seed_state", "rotate"]
