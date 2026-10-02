"""Database cleanup background tasks."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from sqlalchemy import delete

from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.models.refresh_token import RefreshToken
from app.workers.celery_app import celery_app

logger = get_logger("worker_cleanup")


async def _cleanup_expired_tokens() -> int:
    """Delete expired refresh tokens while retaining revoked tokens for reuse detection."""
    now = datetime.now(timezone.utc)
    async with get_session_factory()() as session:
        stmt = delete(RefreshToken).where(RefreshToken.expires_at < now)
        res = await session.execute(stmt)
        await session.commit()
        deleted_tokens = res.rowcount or 0

    from app.core.redis import get_redis_client

    redis = get_redis_client()
    deleted_reset_keys = 0
    async for key in redis.scan_iter(match="pwd_reset:*", count=500):
        if await redis.ttl(key) <= 0:
            deleted_reset_keys += await redis.delete(key)
    return deleted_tokens + deleted_reset_keys


@celery_app.task(name="app.workers.tasks_cleanup.cleanup_expired_tokens_task")
def cleanup_expired_tokens_task() -> int:
    """Periodic task removing stale refresh tokens."""
    logger.info("Starting expired refresh tokens cleanup")
    count = asyncio.run(_cleanup_expired_tokens())
    logger.info("Finished expired tokens cleanup", deleted_count=count)
    return count
