"""Abstract base game engine driving real-time round lifecycles with standard hooks."""

from __future__ import annotations

import abc
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.constants import GameRoundLifecycle, RoundStatus
from app.core.logging import get_logger
from app.games.base.settlement import RoundSettlementManager
from app.games.base.state import RedisRoundStateManager
from app.models.game import GameRound
from app.repositories.round_repo import RoundRepository
from app.repositories.game_repo import GameRepository
from app.services.fairness_service import FairnessService

logger = get_logger("game_engine")


class BaseGameEngine(abc.ABC):
    """Abstract base class for real-time game engines.

    Implements round lifecycle hooks:
    - open(round_obj): open betting window, publish commitment, write Redis state
    - lock(round_obj): close betting window, transition to RUNNING
    - resolve(round_obj): derive provably fair outcome
    - settle(round_obj, outcome): batch settle wagers idempotently
    - history(round_obj, outcome): complete round, reveal seed, update history
    """

    def __init__(
        self,
        game_id: str,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis,
        betting_duration_sec: float = 10.0,
        intermission_duration_sec: float = 3.0,
    ) -> None:
        self.game_id = game_id
        self.session_factory = session_factory
        self.redis = redis
        self.channel_name = f"game:{game_id}"
        self.settlement_mgr = RoundSettlementManager(session_factory)
        self.state_mgr = RedisRoundStateManager(redis)

        self.betting_duration = betting_duration_sec
        self.intermission_duration = intermission_duration_sec

        self._running = False
        self._current_round: Optional[GameRound] = None
        self._loop_task: Optional[asyncio.Task] = None

    @property
    def current_round(self) -> Optional[GameRound]:
        return self._current_round

    @property
    def is_running(self) -> bool:
        return self._running

    async def publish_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        round_id: Optional[str] = None,
    ) -> None:
        """Publish versioned event envelope: {v, type, round_id, data, ts} to Redis pub/sub."""
        envelope = {
            "v": 1,
            "type": event_type,
            "game_id": self.game_id,
            "round_id": round_id or (self._current_round.id if self._current_round else None),
            "data": payload,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await self.redis.publish(self.channel_name, json.dumps(envelope))
        except Exception as exc:
            logger.warning(
                "Failed to publish game event to Redis",
                game_id=self.game_id,
                event=event_type,
                error=str(exc),
            )

    async def prepare_next_round(
        self, initial_status: str = RoundStatus.BETTING.value
    ) -> GameRound:
        """Create a new provably-fair round in database with pre-game commitment."""
        async with self.session_factory() as session:
            round_repo = RoundRepository(session)
            fairness_svc = FairnessService(session)

            latest = await round_repo.get_latest_round(self.game_id)
            next_round_no = (latest.round_no + 1) if latest else 1

            # Commit-reveal: generate seed and publish hash BEFORE betting starts
            round_obj = await fairness_svc.create_round_seed(
                game_id=self.game_id,
                round_no=next_round_no,
            )
            round_obj.status = initial_status
            round_obj.started_at = datetime.now(timezone.utc)
            await session.commit()
            self._current_round = round_obj
            return round_obj

    async def is_game_enabled(self) -> bool:
        """Read the administrative enabled flag before creating another round."""
        async with self.session_factory() as session:
            game = await GameRepository(session).get_by_id(self.game_id)
            return bool(game and game.is_active)

    # ---------------------------------------------------------
    # Lifecycle Hooks: open, lock, resolve, settle, history
    # ---------------------------------------------------------

    async def open(self, round_obj: GameRound) -> None:
        """Hook: Open round for betting, publish commitment, and store Redis state."""
        # 1. Update Redis state
        await self.state_mgr.set_round_state(
            game_id=self.game_id,
            round_id=round_obj.id,
            round_no=round_obj.round_no,
            status=RoundStatus.BETTING.value,
            server_seed_hash=round_obj.server_seed_hash,
            started_at=round_obj.started_at,
        )

        # 2. Publish open event
        await self.publish_event(
            "ROUND_BETTING_OPEN",
            {
                "round_no": round_obj.round_no,
                "server_seed_hash": round_obj.server_seed_hash,
                "status": RoundStatus.BETTING.value,
            },
            round_id=round_obj.id,
        )

        # 3. Betting window countdown
        for remaining in range(int(self.betting_duration), 0, -1):
            if not self._running:
                break
            await self.publish_event(
                "BETTING_COUNTDOWN",
                {"seconds_left": remaining},
                round_id=round_obj.id,
            )
            await asyncio.sleep(1.0)

    async def lock(self, round_obj: GameRound) -> None:
        """Hook: Close betting window and transition round to RUNNING."""
        async with self.session_factory() as session:
            round_repo = RoundRepository(session)
            await round_repo.update_status(
                round_id=round_obj.id,
                status=RoundStatus.RUNNING.value,
                started_at=datetime.now(timezone.utc),
            )
            await session.commit()

        await self.state_mgr.update_status(self.game_id, RoundStatus.RUNNING.value)

        await self.publish_event(
            "ROUND_STARTED",
            {
                "round_no": round_obj.round_no,
                "status": RoundStatus.RUNNING.value,
            },
            round_id=round_obj.id,
        )

    @abc.abstractmethod
    async def resolve(self, round_obj: GameRound) -> Dict[str, Any]:
        """Hook: Compute provably-fair outcome for this round."""
        pass

    @abc.abstractmethod
    async def settle(self, round_obj: GameRound, outcome: Dict[str, Any]) -> None:
        """Hook: Settle player entries through wallet service in batches."""
        pass

    async def history(self, round_obj: GameRound, outcome: Dict[str, Any]) -> None:
        """Hook: Complete round, reveal server seed, clear Redis state, publish result."""
        async with self.session_factory() as session:
            fairness_svc = FairnessService(session)
            revealed = await fairness_svc.reveal_seed(round_obj.id)
            await session.commit()

        await self.state_mgr.clear_round_state(self.game_id)

        await self.publish_event(
            "ROUND_COMPLETED",
            {
                "round_no": round_obj.round_no,
                "server_seed": revealed["server_seed"],
                "server_seed_hash": revealed["server_seed_hash"],
                "outcome": outcome,
                "status": RoundStatus.COMPLETED.value,
            },
            round_id=round_obj.id,
        )

    async def run_round_cycle(self) -> None:
        """Standard lifecycle execution cycle."""
        round_obj = await self.prepare_next_round()
        await self.open(round_obj)
        await self.lock(round_obj)
        outcome = await self.resolve(round_obj)
        await self.settle(round_obj, outcome)
        await self.history(round_obj, outcome)
        await asyncio.sleep(self.intermission_duration)

    async def _main_loop(self) -> None:
        """Continuous round execution loop while engine is running."""
        logger.info("Starting engine loop", game_id=self.game_id)
        while self._running:
            try:
                if not await self.is_game_enabled():
                    await asyncio.sleep(1.0)
                    continue
                await self.run_round_cycle()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    "Error during round cycle execution",
                    game_id=self.game_id,
                    error=str(exc),
                    exc_info=True,
                )
                await asyncio.sleep(2.0)

    def start(self) -> asyncio.Task:
        """Start the engine loop as an asyncio Task."""
        if not self._running:
            self._running = True
            self._loop_task = asyncio.create_task(self._main_loop())
        return self._loop_task

    async def stop(self) -> None:
        """Gracefully stop the engine loop."""
        self._running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        self._loop_task = None
        logger.info("Engine loop stopped", game_id=self.game_id)


# -------------------------------------------------------------
# Runner entrypoint: python -m app.games.base.engine
# -------------------------------------------------------------

async def run_engine_runner() -> None:
    """Standalone runner: leader election + all game engines + cricket sync."""
    from app.core.database import close_db, get_session_factory, init_db
    from app.core.redis import close_redis, init_redis
    from app.games.runtime import run_game_runtime

    logger.info("Starting Game Engine Runner...")
    await init_db()
    redis = await init_redis()

    if redis is None:
        logger.error("Redis is not available. Engine runner requires Redis for leader election and state management.")
        await close_db()
        return

    try:
        await run_game_runtime(get_session_factory(), redis)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received")
    finally:
        await close_redis()
        await close_db()


if __name__ == "__main__":
    asyncio.run(run_engine_runner())
