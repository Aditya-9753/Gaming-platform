"""WebSocket routes for game streams, user events, tickets, and state resync."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.logging import get_logger
from app.core.redis import get_redis_client
from app.games.base.state import RedisRoundStateManager
from app.websocket.auth import authenticate_websocket, create_ws_ticket
from app.websocket.events import format_ws_event
from app.websocket.manager import ws_manager

logger = get_logger("ws_routes")

router = APIRouter(tags=["WebSocket"])


# =========================================================================
# REST Ticket Issuance Endpoint
# =========================================================================


@router.post("/ws/ticket")
async def issue_websocket_ticket(
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Issue a single-use, 60-second ticket for secure WebSocket connection."""
    redis = get_redis_client()
    ticket = await create_ws_ticket(redis, current_user.id, ttl_seconds=60)
    return {
        "ticket": ticket,
        "expires_in": 60,
        "user_id": current_user.id,
    }


# =========================================================================
# WebSocket Endpoints
# =========================================================================


@router.websocket("/ws/games/{game_id}")
async def websocket_game_stream(websocket: WebSocket, game_id: str) -> None:
    """Real-time multiplayer stream for game rounds, countdowns, and multiplier ticks.

    Features:
    - Ticket-based authentication with JWT fallback (or anonymous spectator).
    - Immediate state snapshot sent on connect for resync.
    - Heartbeat PING/PONG.
    - Per-connection message rate limiting.
    """
    redis = get_redis_client()
    user_id = await authenticate_websocket(websocket, required=False, redis=redis)
    channel = f"game:{game_id}"
    await ws_manager.connect(websocket, channel=channel, user_id=user_id)

    # 1. Send initial CONNECTED envelope
    await websocket.send_text(
        format_ws_event(
            "CONNECTED",
            {"game_id": game_id, "user_id": user_id, "status": "LIVE"},
            game_id=game_id,
        )
    )

    # 2. Resync: send current active round state snapshot if available
    try:
        state_mgr = RedisRoundStateManager(redis)
        snapshot = await state_mgr.get_round_state(game_id)
        if snapshot:
            await websocket.send_text(
                format_ws_event(
                    "STATE_SNAPSHOT",
                    snapshot.to_dict(),
                    round_id=snapshot.round_id,
                    game_id=game_id,
                )
            )
    except Exception as exc:
        logger.warning("Could not send initial state snapshot", game_id=game_id, error=str(exc))

    # 3. Connection loop
    try:
        while True:
            raw_text = await websocket.receive_text()

            # Enforce per-connection rate limit
            if not ws_manager.check_rate_limit(websocket):
                await websocket.send_text(
                    format_ws_event(
                        "ERROR",
                        {"message": "Rate limit exceeded. Too many messages per second."},
                        game_id=game_id,
                    )
                )
                continue

            try:
                data = json.loads(raw_text)
                msg_type = data.get("type", "").upper()
                if msg_type == "PING":
                    await websocket.send_text(
                        format_ws_event("PONG", {"ts": datetime.now(timezone.utc).isoformat()}, game_id=game_id)
                    )
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WebSocket game stream error", game_id=game_id, error=str(exc))
    finally:
        await ws_manager.disconnect(websocket, channel=channel, user_id=user_id)


@router.websocket("/ws/user")
async def websocket_user_stream(websocket: WebSocket) -> None:
    """Private authenticated WebSocket stream for balance, bet, and alert notifications."""
    redis = get_redis_client()
    user_id = await authenticate_websocket(websocket, required=True, redis=redis)
    if not user_id:
        return

    await ws_manager.connect(websocket, user_id=user_id)
    await websocket.send_text(
        format_ws_event("CONNECTED", {"user_id": user_id, "channel": "user"})
    )

    try:
        while True:
            raw_text = await websocket.receive_text()

            if not ws_manager.check_rate_limit(websocket):
                await websocket.send_text(
                    format_ws_event("ERROR", {"message": "Rate limit exceeded."})
                )
                continue

            try:
                data = json.loads(raw_text)
                if data.get("type", "").upper() == "PING":
                    await websocket.send_text(
                        format_ws_event("PONG", {"ts": datetime.now(timezone.utc).isoformat()})
                    )
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WebSocket user stream error", user_id=user_id, error=str(exc))
    finally:
        await ws_manager.disconnect(websocket, user_id=user_id)


@router.websocket("/ws/notifications")
async def websocket_notifications_stream(websocket: WebSocket) -> None:
    """Dedicated authenticated WebSocket stream for real-time notifications (result, system, account)."""
    redis = get_redis_client()
    user_id = await authenticate_websocket(websocket, required=True, redis=redis)
    if not user_id:
        return

    await ws_manager.connect(websocket, user_id=user_id)
    await websocket.send_text(
        format_ws_event(
            "CONNECTED",
            {"user_id": user_id, "channel": "notifications", "status": "READY"},
        )
    )

    try:
        while True:
            raw_text = await websocket.receive_text()

            if not ws_manager.check_rate_limit(websocket):
                await websocket.send_text(
                    format_ws_event("ERROR", {"message": "Rate limit exceeded."})
                )
                continue

            try:
                data = json.loads(raw_text)
                if data.get("type", "").upper() == "PING":
                    await websocket.send_text(
                        format_ws_event("PONG", {"ts": datetime.now(timezone.utc).isoformat()})
                    )
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WebSocket notifications stream error", user_id=user_id, error=str(exc))
    finally:
        await ws_manager.disconnect(websocket, user_id=user_id)
