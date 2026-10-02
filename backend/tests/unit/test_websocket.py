"""Unit tests for WebSocket event formatting, manager, and auth."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from starlette.websockets import WebSocketDisconnect

from app.websocket.routes import websocket_notifications_stream
from app.websocket.events import WSEventType, format_ws_event
from app.websocket.manager import ConnectionManager


def test_format_ws_event():
    """Verify WebSocket message serialization."""
    frame = format_ws_event("ROUND_STARTED", {"round_id": "r-123"}, game_id="aviator")
    parsed = json.loads(frame)
    assert parsed["type"] == "ROUND_STARTED"
    assert parsed["game_id"] == "aviator"
    assert parsed["data"]["round_id"] == "r-123"
    assert "timestamp" in parsed


@pytest.mark.asyncio
async def test_connection_manager_broadcast():
    """Verify ConnectionManager room grouping and message broadcasting."""
    manager = ConnectionManager()
    ws1 = MagicMock()
    ws1.accept = AsyncMock()
    ws1.send_text = AsyncMock()

    ws2 = MagicMock()
    ws2.accept = AsyncMock()
    ws2.send_text = AsyncMock()

    # Connect ws1 to aviator, ws2 to color
    await manager.connect(ws1, game_id="aviator", user_id="u1")
    await manager.connect(ws2, game_id="color", user_id="u2")

    msg = format_ws_event("TICK", {"multiplier": 1.25}, game_id="aviator")
    await manager.broadcast_to_game("aviator", msg)

    ws1.send_text.assert_awaited_once_with(msg)
    ws2.send_text.assert_not_awaited()

    # Disconnect
    await manager.disconnect(ws1, game_id="aviator", user_id="u1")
    await manager.broadcast_to_game("aviator", msg)
    # Still only 1 call
    assert ws1.send_text.await_count == 1


@pytest.mark.asyncio
async def test_connection_manager_send_to_user():
    """Verify direct user socket messaging."""
    manager = ConnectionManager()
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()

    await manager.connect(ws, user_id="user_target")
    msg = json.dumps({"type": "WALLET_UPDATE", "balance": 5000})
    await manager.send_to_user("user_target", msg)

    ws.send_text.assert_awaited_once_with(msg)


@pytest.mark.asyncio
async def test_notifications_websocket_authenticates_and_handles_ping(monkeypatch):
    """The dedicated notifications route authenticates and accepts client heartbeats."""
    from app.websocket import routes

    websocket = MagicMock()
    websocket.send_text = AsyncMock()
    websocket.receive_text = AsyncMock(
        side_effect=['{"type":"PING"}', WebSocketDisconnect(code=1000)]
    )
    monkeypatch.setattr(routes, "get_redis_client", lambda: None)
    monkeypatch.setattr(
        routes,
        "authenticate_websocket",
        AsyncMock(return_value="notification-user"),
    )
    monkeypatch.setattr(routes.ws_manager, "connect", AsyncMock())
    monkeypatch.setattr(routes.ws_manager, "disconnect", AsyncMock())
    monkeypatch.setattr(routes.ws_manager, "check_rate_limit", lambda _ws: True)

    await websocket_notifications_stream(websocket)

    routes.authenticate_websocket.assert_awaited_once()
    routes.ws_manager.connect.assert_awaited_once_with(
        websocket, user_id="notification-user"
    )
    assert websocket.send_text.await_count == 2
    assert '"type": "CONNECTED"' in websocket.send_text.await_args_list[0].args[0]
    assert '"type": "PONG"' in websocket.send_text.await_args_list[1].args[0]
    routes.ws_manager.disconnect.assert_awaited_once_with(
        websocket, user_id="notification-user"
    )
