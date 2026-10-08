"""Celery distributed task application and periodic beat schedule."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "gaming_platform",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.tasks_reconcile",
        "app.workers.tasks_cleanup",
        "app.workers.tasks_leaderboard",
        "app.workers.tasks_notifications",
        "app.workers.tasks_archive",
        "app.workers.tasks_cricket",
        "app.workers.tasks_affiliate",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 min hard limit
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    beat_schedule={
        "reconcile-wallets-nightly": {
            "task": "app.workers.tasks_reconcile.reconcile_wallets_task",
            "schedule": crontab(minute="0", hour="2"),  # Daily at 02:00 UTC
        },
        "cleanup-tokens-daily": {
            "task": "app.workers.tasks_cleanup.cleanup_expired_tokens_task",
            "schedule": crontab(minute="30", hour="3"),  # Daily at 03:30 UTC
        },
        "archive-old-game-data-daily": {
            "task": "app.workers.tasks_archive.archive_old_rounds_task",
            "schedule": crontab(minute="0", hour="4"),  # Daily at 04:00 UTC
        },
        "refresh-leaderboard-periodic": {
            "task": "app.workers.tasks_leaderboard.refresh_leaderboards_task",
            "schedule": 900.0,  # Every 15 minutes
        },
        "sync-cricket-markets-minute": {
            "task": "app.workers.tasks_cricket.sync_cricket_markets_task",
            "schedule": 60.0,
        },
        # Partner / affiliate platform
        "aff-process-events": {"task": "app.workers.tasks_affiliate.process_events", "schedule": 15.0},
        "aff-commissions": {"task": "app.workers.tasks_affiliate.commissions", "schedule": 60.0},
        "aff-analytics": {"task": "app.workers.tasks_affiliate.analytics", "schedule": 120.0},
        "aff-postbacks": {"task": "app.workers.tasks_affiliate.postbacks", "schedule": 30.0},
        "aff-drain-clicks": {"task": "app.workers.tasks_affiliate.drain_clicks", "schedule": 60.0},
        "aff-internal-revenue": {"task": "app.workers.tasks_affiliate.internal_revenue", "schedule": crontab(minute="5")},
        "aff-periods": {"task": "app.workers.tasks_affiliate.periods", "schedule": crontab(minute="10")},
        "aff-reconcile-nightly": {"task": "app.workers.tasks_affiliate.reconcile", "schedule": crontab(minute="15", hour="2")},
        # ECB publishes around 16:00 CET on working days
        "aff-fx-rates": {"task": "app.workers.tasks_affiliate.fx_rates", "schedule": crontab(minute="30", hour="15,21")},
        "aff-click-partitions": {"task": "app.workers.tasks_affiliate.partitions", "schedule": crontab(minute="20", hour="1")},
    },
)
