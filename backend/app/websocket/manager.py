"""WebSocket connection manager with channel routing and per-connection rate limiting."""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional, Set
from fastapi import WebSocket

from app.core.logging import get_logger

logger = get_logger("ws_manager")


class ConnectionManager:
    """Manages active WebSockets grouped by channel/room, user, and enforces rate limits."""

    def __init__(self, max_msgs_per_second: int = 15) -> None:
        # channel_name -> set of connected WebSockets
        self._channels: Dict[str, Set[WebSocket]] = {}
        # user_id -> set of connected WebSockets
        self._user_sockets: Dict[str, Set[WebSocket]] = {}
        # websocket -> list of recent message timestamps (for per-connection rate limiting)
        self._msg_history: Dict[WebSocket, List[float]] = {}
        self.max_msgs_per_second = max_msgs_per_second
        self._lock = asyncio.Lock()

    @property
    def active_connection_count(self) -> int:
        """Return the count of currently registered WebSocket connections."""
        return len(self._msg_history)

    async def connect(
        self,
        websocket: WebSocket,
        channel: Optional[str] = None,
        user_id: Optional[str] = None,
        game_id: Optional[str] = None,
    ) -> None:
        """Accept WebSocket and register under channel and/or user."""
        await websocket.accept()
        if not channel and game_id:
            channel = f"game:{game_id}"

        async with self._lock:
            if channel:
                if channel not in self._channels:
                    self._channels[channel] = set()
                self._channels[channel].add(websocket)

            if user_id:
                if user_id not in self._user_sockets:
                    self._user_sockets[user_id] = set()
                self._user_sockets[user_id].add(websocket)

            self._msg_history[websocket] = []

        logger.info(
            "WebSocket connected",
            channel=channel,
            user_id=user_id,
            total_channel_conns=len(self._channels.get(channel, set())) if channel else 0,
        )

    async def disconnect(
        self,
        websocket: WebSocket,
        channel: Optional[str] = None,
        user_id: Optional[str] = None,
        game_id: Optional[str] = None,
    ) -> None:
        """Unregister a disconnected WebSocket and free its rate limit buffer."""
        if not channel and game_id:
            channel = f"game:{game_id}"

        async with self._lock:
            if channel and channel in self._channels:
                self._channels[channel].discard(websocket)
                if not self._channels[channel]:
                    del self._channels[channel]

            if user_id and user_id in self._user_sockets:
                self._user_sockets[user_id].discard(websocket)
                if not self._user_sockets[user_id]:
                    del self._user_sockets[user_id]

            self._msg_history.pop(websocket, None)

        logger.info("WebSocket disconnected", channel=channel, user_id=user_id)

    def check_rate_limit(self, websocket: WebSocket) -> bool:
        """Return False if client sent more than max_msgs_per_second within a 1-second window."""
        now = time.monotonic()
        history = self._msg_history.setdefault(websocket, [])
        # Retain only timestamps from the last 1.0 second
        self._msg_history[websocket] = [t for t in history if now - t < 1.0]

        if len(self._msg_history[websocket]) >= self.max_msgs_per_second:
            return False

        self._msg_history[websocket].append(now)
        return True

    async def broadcast_to_channel(self, channel: str, message: str) -> None:
        """Broadcast message to all WebSockets listening on a channel."""
        async with self._lock:
            sockets = set(self._channels.get(channel, set()))

        if not sockets:
            return

        dead_sockets = set()
        for ws in sockets:
            try:
                await ws.send_text(message)
            except Exception:
                dead_sockets.add(ws)

        if dead_sockets:
            async with self._lock:
                if channel in self._channels:
                    self._channels[channel] -= dead_sockets
                for d in dead_sockets:
                    self._msg_history.pop(d, None)

    async def broadcast_to_game(self, game_id: str, message: str) -> None:
        """Convenience alias for broadcasting to a game channel."""
        await self.broadcast_to_channel(f"game:{game_id}", message)

    async def send_to_user(self, user_id: str, message: str) -> None:
        """Send message directly to all active connections belonging to a user."""
        async with self._lock:
            sockets = set(self._user_sockets.get(user_id, set()))

        if not sockets:
            return

        dead_sockets = set()
        for ws in sockets:
            try:
                await ws.send_text(message)
            except Exception:
                dead_sockets.add(ws)

        if dead_sockets:
            async with self._lock:
                if user_id in self._user_sockets:
                    self._user_sockets[user_id] -= dead_sockets
                for d in dead_sockets:
                    self._msg_history.pop(d, None)


# Global connection manager instance
ws_manager = ConnectionManager()
