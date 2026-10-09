"""Affiliate background jobs, shared by Celery tasks (production) and the in-process loop (development)."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.affiliate import analytics, commission, ingest, ledger, operator_bridge, postbacks, settlement, tracking
from app.affiliate import settings as aff_settings
from app.affiliate.common import SYSTEM
from app.core.logging import get_logger

logger = get_logger("aff_jobs")


async def process_events(db: AsyncSession) -> int:
    """Outbox / RECEIVED events, then retry FAILED ones."""
    done = await operator_bridge.process_outbox(db)
    done += await ingest.retry_failed(db)
    return done


async def commissions(db: AsyncSession) -> int:
    return await commission.process_dirty_revenue(db)


async def analytics_rollup(db: AsyncSession) -> int:
    return await analytics.rebuild_dirty(db) + await analytics.rebuild_today(db)


async def deliver_postbacks(db: AsyncSession) -> int:
    return await postbacks.send_pending(db)


async def drain_clicks(db: AsyncSession) -> int:
    try:
        return await tracking.drain_backlog(db)
    except Exception:  # Redis down: nothing was queued there either
        return 0


async def internal_revenue(db: AsyncSession) -> int:
    await operator_bridge.sync_today(db)
    return 0


async def periods(db: AsyncSession) -> int:
    await commission.ensure_current_period(db)
    await db.commit()
    if await aff_settings.get(db, "auto_close_periods"):
        return len(await settlement.auto_close_due(db, SYSTEM))
    return 0


async def fx_rates(db: AsyncSession) -> int:
    from app.affiliate import fx
    from app.core.config import get_settings

    if not get_settings().AFFILIATE_FX_AUTO_FETCH:
        return 0
    return int((await fx.sync_rates(db))["currencies"])


async def reconcile(db: AsyncSession) -> int:
    mismatches = await ledger.reconcile(db)
    await db.commit()
    if mismatches:
        logger.error("Affiliate ledger mismatch", count=len(mismatches))
    return len(mismatches)


async def partitions(db: AsyncSession) -> int:
    """PostgreSQL: make sure next month's click partition exists (no-op elsewhere)."""
    if db.bind.dialect.name != "postgresql":
        return 0
    from sqlalchemy import text

    await db.execute(text("SELECT aff_ensure_click_partitions(3)"))
    # new partitions get row level security like every other table
    has_rls_fn = (await db.execute(text("SELECT to_regproc('aff_enable_rls') IS NOT NULL"))).scalar()
    if has_rls_fn:
        await db.execute(text("SELECT aff_enable_rls()"))
    await db.commit()
    return 1


JOBS: Dict[str, Callable[[AsyncSession], Awaitable[int]]] = {
    "process_events": process_events,
    "commissions": commissions,
    "analytics": analytics_rollup,
    "postbacks": deliver_postbacks,
    "drain_clicks": drain_clicks,
    "internal_revenue": internal_revenue,
    "periods": periods,
    "reconcile": reconcile,
    "fx_rates": fx_rates,
    "partitions": partitions,
}


async def run(factory: async_sessionmaker, name: str) -> int:
    async with factory() as db:
        try:
            return await JOBS[name](db)
        except Exception as exc:
            await db.rollback()
            logger.error("Affiliate job failed", job=name, error=str(exc))
            return 0


async def dev_loop(factory: async_sessionmaker) -> None:
    """Development: run every job on a schedule inside the API process (production uses Celery beat)."""
    # fx_rates first so conversions work from the first processed event
    schedule = {"fx_rates": 6 * 3600, "process_events": 15, "commissions": 30, "analytics": 60, "postbacks": 30, "drain_clicks": 60,
                "internal_revenue": 900, "periods": 3600, "reconcile": 6 * 3600, "partitions": 24 * 3600}
    elapsed = 0
    await asyncio.sleep(5)
    while True:
        for name, every in schedule.items():
            if elapsed % every == 0:
                await run(factory, name)
        await asyncio.sleep(15)
        elapsed += 15
