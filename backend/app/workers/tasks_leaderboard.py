"""Leaderboard aggregation background task."""

from __future__ import annotations

import asyncio
from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.services.leaderboard_service import LeaderboardService
from app.workers.celery_app import celery_app

logger = get_logger("worker_leaderboard")


async def run_leaderboard_refresh() -> int:
    """Compute and refresh platform leaderboards for daily and weekly windows."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        svc = LeaderboardService(session)
        daily_count = await svc.refresh_leaderboard(period="DAILY")
        weekly_count = await svc.refresh_leaderboard(period="WEEKLY")
        all_time_count = await svc.refresh_leaderboard(period="ALL_TIME")
        total = daily_count + weekly_count + all_time_count
        logger.info(
            "Leaderboard refresh complete",
            daily=daily_count,
            weekly=weekly_count,
            all_time=all_time_count,
        )
        return total


@celery_app.task(name="app.workers.tasks_leaderboard.refresh_leaderboards_task")
def refresh_leaderboards_task() -> int:
    """Periodic task updating daily, weekly, and all-time leaderboards."""
    logger.info("Starting scheduled leaderboard aggregation")
    count = asyncio.run(run_leaderboard_refresh())
    logger.info("Finished leaderboard aggregation", total_entries=count)
    return count
