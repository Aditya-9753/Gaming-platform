"""Synchronize live Cricket fixtures and settle completed winner markets."""

from __future__ import annotations

import asyncio

from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.core.redis import get_redis_client
from app.games.cricket.market_service import CricketMarketService, get_cricket_provider
from app.workers.celery_app import celery_app

logger = get_logger("worker_cricket")


async def _sync_cricket_markets() -> int:
    async with get_session_factory()() as session:
        service = CricketMarketService(
            session,
            provider=get_cricket_provider(),
            redis=get_redis_client(),
        )
        return await service.sync_and_settle()


@celery_app.task(name="app.workers.tasks_cricket.sync_cricket_markets_task")
def sync_cricket_markets_task() -> int:
    logger.info("Starting Cricket provider synchronization")
    count = asyncio.run(_sync_cricket_markets())
    logger.info("Finished Cricket provider synchronization", settled=count)
    return count
