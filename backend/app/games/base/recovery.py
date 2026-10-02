"""Startup recovery service for interrupted and unsettled game rounds."""

from __future__ import annotations

from typing import Callable, Coroutine, List, Optional
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.constants import GameRoundLifecycle, RoundStatus
from app.core.logging import get_logger
from app.games.base.settlement import RoundSettlementManager
from app.games.base.state import RedisRoundStateManager
from app.models.game import GameRound

logger = get_logger("engine_recovery")


class EngineRecoveryService:
    """Recovers stale or abandoned game rounds upon server/engine startup."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Optional[Redis] = None,
    ) -> None:
        self.session_factory = session_factory
        self.redis = redis
        self.settlement_mgr = RoundSettlementManager(session_factory)
        self.state_mgr = RedisRoundStateManager(redis) if redis else None

    async def recover_orphaned_rounds(self, game_ids: Optional[List[str]] = None) -> int:
        """Scan for rounds stuck in SCHEDULED, BETTING, or RUNNING status and refund wagers.

        ``game_ids`` limits recovery to engine-driven games; player-driven games
        such as Mines keep RUNNING rounds legitimately between requests.
        """
        orphaned_statuses = [
            RoundStatus.SCHEDULED.value,
            GameRoundLifecycle.WAITING.value,
            RoundStatus.BETTING.value,
            GameRoundLifecycle.BETTING_OPEN.value,
            GameRoundLifecycle.CREATED.value,
            GameRoundLifecycle.OPEN.value,
            GameRoundLifecycle.LOCKED.value,
            RoundStatus.RUNNING.value,
            GameRoundLifecycle.CRASHED.value,
            GameRoundLifecycle.SETTLING.value,
            GameRoundLifecycle.RESULT.value,
            GameRoundLifecycle.SETTLED.value,
        ]

        async with self.session_factory() as session:
            stmt = select(GameRound).where(GameRound.status.in_(orphaned_statuses))
            if game_ids is not None:
                stmt = stmt.where(GameRound.game_id.in_(game_ids))
            res = await session.execute(stmt)
            orphaned_rounds: List[GameRound] = list(res.scalars().all())

        if not orphaned_rounds:
            logger.info("Engine recovery check: zero orphaned rounds found")
            return 0

        logger.warning(
            "Found orphaned rounds to recover",
            count=len(orphaned_rounds),
            round_ids=[r.id for r in orphaned_rounds],
        )

        recovered_count = 0
        for r in orphaned_rounds:
            try:
                # If round was already resolved with result but crashed before settlement:
                if r.result and r.server_seed:
                    logger.info("Orphaned round has result, completing settlement", round_id=r.id)
                # Otherwise, refund all placed bets cleanly
                await self.settlement_mgr.refund_round(
                    round_id=r.id,
                    reason="ENGINE_STARTUP_RECOVERY",
                )

                if self.state_mgr:
                    await self.state_mgr.clear_round_state(r.game_id)

                recovered_count += 1
                logger.info(
                    "Successfully refunded and cancelled orphaned round",
                    round_id=r.id,
                    game_id=r.game_id,
                )
            except Exception as exc:
                logger.error(
                    "Failed to recover orphaned round",
                    round_id=r.id,
                    error=str(exc),
                    exc_info=True,
                )

        return recovered_count
