"""Distributed leader election using Redis with TTL and heartbeat.

Ensures that only ONE instance of the game engine loop runs across all
distributed API / worker replicas at any given time.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Callable, Coroutine, Optional
from redis.asyncio import Redis

from app.core.logging import get_logger

logger = get_logger("leader_election")

# Lua script to safely release lock only if the value matches current instance ID
RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# Lua script to safely renew lock TTL only if the value matches current instance ID
RENEW_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("pexpire", KEYS[1], ARGV[2])
else
    return 0
end
"""


class LeaderElection:
    """Manages leadership election for a game engine via Redis distributed lock."""

    def __init__(
        self,
        redis: Redis,
        lock_name: str,
        ttl_seconds: int = 10,
        heartbeat_interval: float = 3.0,
    ) -> None:
        self.redis = redis
        self.lock_key = f"leader:lock:{lock_name}"
        self.ttl_ms = int(ttl_seconds * 1000)
        self.heartbeat_interval = heartbeat_interval
        self.instance_id = str(uuid.uuid4())
        self._is_leader = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

    @property
    def is_leader(self) -> bool:
        """Return True if this instance is currently the elected leader."""
        return self._is_leader

    async def acquire(self) -> bool:
        """Attempt to acquire the leader lock."""
        try:
            acquired = await self.redis.set(
                self.lock_key,
                self.instance_id,
                nx=True,
                px=self.ttl_ms,
            )
            if acquired:
                self._is_leader = True
                logger.info(
                    "Acquired game engine leadership",
                    lock=self.lock_key,
                    instance_id=self.instance_id,
                )
                self._start_heartbeat()
                return True
        except Exception as exc:
            logger.warning("Error acquiring leadership lock", error=str(exc))
        return False

    async def renew(self) -> bool:
        """Extend lock TTL if still the leader."""
        try:
            res = await self.redis.eval(
                RENEW_LUA, 1, self.lock_key, self.instance_id, self.ttl_ms
            )
            return res == 1
        except Exception:
            # Fallback for environments where Lua eval is unavailable (e.g. fakeredis)
            try:
                val = await self.redis.get(self.lock_key)
                if val == self.instance_id:
                    await self.redis.pexpire(self.lock_key, self.ttl_ms)
                    return True
            except Exception:
                pass
            return False

    async def release(self) -> None:
        """Safely release the leader lock."""
        self._stop_heartbeat()
        if not self._is_leader:
            return

        try:
            await self.redis.eval(
                RELEASE_LUA, 1, self.lock_key, self.instance_id
            )
            logger.info(
                "Released game engine leadership",
                lock=self.lock_key,
                instance_id=self.instance_id,
            )
        except Exception:
            # Fallback for environments where Lua eval is unavailable (e.g. fakeredis)
            try:
                val = await self.redis.get(self.lock_key)
                if val == self.instance_id:
                    await self.redis.delete(self.lock_key)
            except Exception:
                pass
        finally:
            self._is_leader = False

    def _start_heartbeat(self) -> None:
        """Start background task to renew lock TTL periodically."""
        self._stop_heartbeat()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    def _stop_heartbeat(self) -> None:
        """Stop background heartbeat task."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        """Renew lock TTL on interval; step down if renewal fails."""
        try:
            while self._is_leader:
                await asyncio.sleep(self.heartbeat_interval)
                success = await self.renew()
                if not success:
                    logger.warning(
                        "Failed to renew leadership lock; stepping down",
                        lock=self.lock_key,
                    )
                    self._is_leader = False
                    break
        except asyncio.CancelledError:
            pass

    async def run_leadership_loop(
        self,
        on_leadership_acquired: Callable[[], Coroutine[Any, Any, None]],
        check_interval: float = 2.0,
    ) -> None:
        """Keep attempting to become leader and execute workload once acquired."""
        self._running = True
        logger.info(
            "Starting leadership election monitor",
            lock=self.lock_key,
            instance_id=self.instance_id,
        )

        try:
            while self._running:
                if not self._is_leader:
                    acquired = await self.acquire()
                    if acquired:
                        try:
                            # Run workload until leadership is lost or task cancelled
                            await on_leadership_acquired()
                        except asyncio.CancelledError:
                            break
                        except Exception as exc:
                            logger.error(
                                "Error during leader execution",
                                error=str(exc),
                                exc_info=True,
                            )
                        finally:
                            await self.release()
                await asyncio.sleep(check_interval)
        finally:
            await self.release()

    def stop(self) -> None:
        """Signal the leadership monitor to terminate."""
        self._running = False
        self._stop_heartbeat()
