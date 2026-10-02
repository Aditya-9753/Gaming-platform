"""Async Redis client setup, lifecycle management, and health checking."""

from typing import AsyncGenerator, Optional
from redis.asyncio import Redis, from_url

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("redis")

redis_client: Optional[Redis] = None


def get_redis_client() -> Redis:
    """Return the active async Redis client instance.

    Creates client on-demand if not already initialized.
    """
    global redis_client
    if redis_client is None:
        settings = get_settings()
        redis_client = from_url(
            settings.REDIS_URL,
            decode_responses=True,
            health_check_interval=30,
        )
    return redis_client


async def init_redis() -> Optional[Redis]:
    """Initialize Redis connection and test ping.

    Returns the client when reachable, otherwise None.
    """
    client = get_redis_client()
    try:
        await client.ping()
        logger.info("Connected to Redis successfully")
        return client
    except Exception as exc:
        logger.warning("Redis ping failed during startup", error=str(exc))
        return None


async def close_redis() -> None:
    """Close active Redis connection pool."""
    global redis_client
    if redis_client is not None:
        await redis_client.close()
        redis_client = None
        logger.info("Redis connection closed")


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency yielding the async Redis client."""
    client = get_redis_client()
    yield client


import asyncio


async def _run_redis_ping() -> bool:
    client = get_redis_client()
    pong = await client.ping()
    return bool(pong)


async def check_redis_health(timeout: float = 2.0) -> bool:
    """Verify Redis availability with a PING command and timeout."""
    try:
        return await asyncio.wait_for(_run_redis_ping(), timeout=timeout)
    except Exception as exc:
        logger.warning("Redis health check failed", error=str(exc))
        return False

