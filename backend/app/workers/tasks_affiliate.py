"""Celery tasks for the partner / affiliate platform (see app.affiliate.jobs)."""

from __future__ import annotations

import asyncio

from app.core.database import close_db, get_session_factory
from app.workers.celery_app import celery_app


async def _main(name: str) -> int:
    from app.affiliate import jobs

    try:
        return await jobs.run(get_session_factory(), name)
    finally:
        await close_db()  # each task gets its own event loop; never reuse a pool across loops


def _run(name: str) -> int:
    return asyncio.run(_main(name))


@celery_app.task(name="app.workers.tasks_affiliate.process_events")
def process_events_task() -> int:
    return _run("process_events")


@celery_app.task(name="app.workers.tasks_affiliate.commissions")
def commissions_task() -> int:
    return _run("commissions")


@celery_app.task(name="app.workers.tasks_affiliate.analytics")
def analytics_task() -> int:
    return _run("analytics")


@celery_app.task(name="app.workers.tasks_affiliate.postbacks")
def postbacks_task() -> int:
    return _run("postbacks")


@celery_app.task(name="app.workers.tasks_affiliate.drain_clicks")
def drain_clicks_task() -> int:
    return _run("drain_clicks")


@celery_app.task(name="app.workers.tasks_affiliate.internal_revenue")
def internal_revenue_task() -> int:
    return _run("internal_revenue")


@celery_app.task(name="app.workers.tasks_affiliate.periods")
def periods_task() -> int:
    return _run("periods")


@celery_app.task(name="app.workers.tasks_affiliate.reconcile")
def reconcile_task() -> int:
    return _run("reconcile")


@celery_app.task(name="app.workers.tasks_affiliate.fx_rates")
def fx_rates_task() -> int:
    return _run("fx_rates")


@celery_app.task(name="app.workers.tasks_affiliate.partitions")
def partitions_task() -> int:
    return _run("partitions")
