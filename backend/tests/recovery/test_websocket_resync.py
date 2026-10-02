"""Reconnect coverage for recovering the active game state over WebSocket."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.websockets import WebSocketDisconnect

from app.games.base.state import RoundStateSnapshot
from app.websocket import routes


@pytest.mark.asyncio
async def test_reconnect_receives_active_round_snapshot(monkeypatch):
    websocket = MagicMock()
    websocket.send_text = AsyncMock()
    websocket.receive_text = AsyncMock(
        side_effect=[WebSocketDisconnect(code=1000)]
    )
    snapshot = RoundStateSnapshot(
        round_id="active-round",
        game_id="aviator",
        round_no=23,
        status="RUNNING",
        server_seed_hash="committed-hash",
        started_at="2026-10-01T18:00:00+00:00",
    )
    state_manager = MagicMock()
    state_manager.get_round_state = AsyncMock(return_value=snapshot)
    monkeypatch.setattr(routes, "get_redis_client", lambda: MagicMock())
    monkeypatch.setattr(routes, "authenticate_websocket", AsyncMock(return_value=None))
    monkeypatch.setattr(routes, "RedisRoundStateManager", lambda _redis: state_manager)
    monkeypatch.setattr(routes.ws_manager, "connect", AsyncMock())
    monkeypatch.setattr(routes.ws_manager, "disconnect", AsyncMock())

    await routes.websocket_game_stream(websocket, "aviator")

    frames = [json.loads(call.args[0]) for call in websocket.send_text.await_args_list]
    assert frames[0]["type"] == "CONNECTED"
    assert frames[1]["type"] == "STATE_SNAPSHOT"
    assert frames[1]["round_id"] == "active-round"
    assert frames[1]["data"]["status"] == "RUNNING"
    assert frames[1]["data"]["server_seed_hash"] == "committed-hash"
