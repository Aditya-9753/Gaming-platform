"""WebSocket versioned event envelope and message serialization."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class WSEventType(str, Enum):
    """Standardized event types for WebSocket messaging."""

    # Connection & state
    CONNECTED = "CONNECTED"
    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    PING = "PING"
    PONG = "PONG"
    ERROR = "ERROR"

    # Game events
    ROUND_BETTING_OPEN = "ROUND_BETTING_OPEN"
    BETTING_COUNTDOWN = "BETTING_COUNTDOWN"
    ROUND_STARTED = "ROUND_STARTED"
    MULTIPLIER_TICK = "MULTIPLIER_TICK"
    PLAYER_CASHOUT = "PLAYER_CASHOUT"
    BET_PLACED = "BET_PLACED"
    ROUND_CRASHED = "ROUND_CRASHED"
    ROUND_COMPLETED = "ROUND_COMPLETED"
    BALL_DELIVERED = "BALL_DELIVERED"

    # User-specific events
    WALLET_UPDATE = "WALLET_UPDATE"
    NOTIFICATION = "NOTIFICATION"


def format_ws_event(
    event_type: str,
    data: Any,
    round_id: Optional[str] = None,
    game_id: Optional[str] = None,
    version: int = 1,
) -> str:
    """Format and serialize payload into standard versioned envelope {v, type, round_id, data, ts}."""
    now_ts = datetime.now(timezone.utc).isoformat()
    payload: Dict[str, Any] = {
        "v": version,
        "type": event_type,
        "round_id": round_id,
        "data": data,
        "ts": now_ts,
        "timestamp": now_ts,
    }
    if game_id:
        payload["game_id"] = game_id
    return json.dumps(payload)
