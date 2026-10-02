"""Redis Pub/Sub bridge forwarding engine events to local WebSocket clients."""

from __future__ import annotations

import asyncio
from typing import Optional
from redis.asyncio import Redis

from app.core.logging import get_logger
from app.websocket.manager import ws_manager

logger = get_logger("pubsub_bridge")


class RedisPubSubBridge:
    """Subscribes to Redis pub/sub and broadcasts events to connected WebSockets."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def _listener_loop(self) -> None:
        """Pattern subscribe to all game:* and user:* channels."""
        pubsub = self.redis.pubsub()
        await pubsub.psubscribe("game:*", "user:*")
        logger.info("Subscribed to Redis pattern channels: game:*, user:*")

        try:
            while self._running:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )
                    if message and message.get("type") == "pmessage":
                        channel: str = message.get("channel", "")
                        data: str = message.get("data", "")
                        if isinstance(data, bytes):
                            data = data.decode("utf-8")

                        if channel.startswith("game:"):
                            game_id = channel.split(":", 1)[1]
                            await ws_manager.broadcast_to_game(game_id, data)
                        elif channel.startswith("user:"):
                            user_id = channel.split(":", 1)[1]
                            await ws_manager.send_to_user(user_id, data)

                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.warning("Error in Redis PubSub bridge loop", error=str(exc))
                    await asyncio.sleep(1.0)
        finally:
            try:
                await pubsub.punsubscribe("game:*", "user:*")
                if hasattr(pubsub, "aclose"):
                    await pubsub.aclose()
                else:
                    await pubsub.close()
            except Exception:
                pass
            logger.info("Redis PubSub bridge stopped")

    def start(self) -> asyncio.Task:
        """Start pubsub listener as background task."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._listener_loop())
        return self._task

    async def stop(self) -> None:
        """Stop pubsub listener."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
