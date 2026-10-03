"""Game runtime: leader-elected real-time engines + cricket feed sync.

Used both by the standalone runner (``python -m app.games.base.engine``) and
in-process by the API in development (see RUN_GAME_ENGINES), so a single
``uvicorn`` command brings every game live. Redis leader election guarantees
only one runtime drives rounds even if several processes start it.
"""

from __future__ import annotations

import asyncio

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger

logger = get_logger("game_runtime")

CRICKET_SYNC_INTERVAL_SEC = 4.0
LEADERBOARD_REFRESH_SEC = 60.0


async def _leaderboard_loop(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Recompute daily / weekly / all-time rankings (replaces the Celery beat job locally)."""
    from app.services.leaderboard_service import LeaderboardService

    while True:
        try:
            async with session_factory() as session:
                service = LeaderboardService(session)
                for period in ("DAILY", "WEEKLY", "ALL_TIME"):
                    await service.refresh_leaderboard(period=period, limit=100)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Leaderboard refresh failed", error=str(exc))
        await asyncio.sleep(LEADERBOARD_REFRESH_SEC)


async def _cricket_sync_loop(
    session_factory: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    """Pull the cricket provider, broadcast live scores and settle finished matches."""
    from app.games.cricket.market_service import CricketMarketService, get_cricket_provider

    provider = get_cricket_provider()
    while True:
        try:
            async with session_factory() as session:
                settled = await CricketMarketService(
                    session, provider=provider, redis=redis
                ).sync_and_settle()
            if settled:
                logger.info("Cricket predictions settled", count=settled)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Cricket sync failed", error=str(exc))
        await asyncio.sleep(CRICKET_SYNC_INTERVAL_SEC)


async def ensure_teen_patti_game(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Create the Teen Patti catalog row + settings on first start (idempotent)."""
    from app.games.teen_patti.rules import DEFAULT_PAYOUT, GAME_ID
    from app.models.game import Game, GameSetting

    async with session_factory() as session:
        game = await session.get(Game, GAME_ID)
        if game is None:
            session.add(Game(
                id=GAME_ID,
                name="Teen Patti",
                type="CARD",
                description="Live Teen Patti: bet on Player A or Player B. New hand every ~30 seconds.",
                is_active=True,
            ))
            await session.flush()
        from sqlalchemy import select

        has_settings = (await session.execute(select(GameSetting.id).where(GameSetting.game_id == GAME_ID))).first()
        if not has_settings:
            session.add(GameSetting(
                game_id=GAME_ID, min_bet=100, max_bet=500_000, house_edge_percent=200,
                config={"payout": DEFAULT_PAYOUT},
            ))
        await session.commit()


async def run_game_runtime(
    session_factory: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    """Recover orphaned rounds, then run all engines while holding leadership."""
    from app.games.base.leader import LeaderElection
    from app.games.base.recovery import EngineRecoveryService
    from app.games.base.registry import engine_registry

    # Import games so their engines self-register
    import app.games.aviator.engine  # noqa: F401
    import app.games.wingo.engine  # noqa: F401  (replaces the legacy colour engine)
    import app.games.teen_patti.engine  # noqa: F401

    from app.games.wingo.rules import MODES as WINGO_MODES

    # Engines this runtime drives. The legacy "color" engine is retired in
    # favour of WinGo but stays registered (imported by the colour package).
    active_codes = ["aviator", *WINGO_MODES, "teen_patti"]

    leader = LeaderElection(redis, lock_name="global_game_engine_leader", ttl_seconds=10)

    async def run_leader_workload() -> None:
        # Recovery only once we own the lock, so we never refund a round that
        # another live leader is still driving.
        recovered = await EngineRecoveryService(
            session_factory, redis=redis
        ).recover_orphaned_rounds(
            # "color" is the retired engine: refund anything it left open
            game_ids=[*active_codes, "color"]
        )
        logger.info("Acquired engine leadership; starting games", recovered_rounds=recovered)
        try:
            await ensure_teen_patti_game(session_factory)
        except Exception as exc:
            logger.error("Could not create the Teen Patti game row", error=str(exc))

        engine_registry.instantiate_all(session_factory, redis, codes=active_codes)
        await engine_registry.start_all()
        from app.core.config import get_settings
        from app.games.simulated_players import SimulatedPlayers

        background = [
            asyncio.create_task(_cricket_sync_loop(session_factory, redis)),
            asyncio.create_task(_leaderboard_loop(session_factory)),
        ]
        if get_settings().simulated_players_enabled:
            background.append(asyncio.create_task(SimulatedPlayers(session_factory, redis, active_codes).run()))
        try:
            while leader.is_leader:
                await asyncio.sleep(1.0)
            logger.warning("Lost engine leadership; stopping games")
        finally:
            for task in background:
                task.cancel()
            for task in background:
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            await engine_registry.stop_all()

    try:
        await leader.run_leadership_loop(on_leadership_acquired=run_leader_workload)
    finally:
        await engine_registry.stop_all()
        await leader.release()
