"""Color Prediction round lifecycle, result derivation, and settlement."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.constants import GameRoundLifecycle
from app.core.logging import get_logger
from app.games.base.engine import BaseGameEngine
from app.games.base.registry import register_game
from app.games.color.rules import compute_colour, round_timing_seconds
from app.models.game import GameEntry, GameRound
from app.repositories.game_repo import GameRepository
from app.repositories.round_repo import RoundRepository

logger = get_logger("color_engine")


@register_game("color")
class ColorEngine(BaseGameEngine):
    """Run timed prediction rounds using configured server-side deadlines."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis,
        betting_duration_sec: float = 25.0,
        intermission_duration_sec: float = 3.0,
    ) -> None:
        super().__init__(
            game_id="color",
            session_factory=session_factory,
            redis=redis,
            betting_duration_sec=betting_duration_sec,
            intermission_duration_sec=intermission_duration_sec,
        )

    async def _settings(self) -> tuple[dict, int]:
        async with self.session_factory() as session:
            settings = await GameRepository(session).get_settings("color")
            if not settings:
                raise ValueError("Color Prediction settings are not configured")
            return settings.config or {}, settings.house_edge_percent

    async def _set_status(
        self, round_obj: GameRound, status: str, started_at: datetime | None = None
    ) -> None:
        async with self.session_factory() as session:
            await RoundRepository(session).update_status(
                round_obj.id,
                status,
                started_at=started_at,
            )
            await session.commit()
        round_obj.status = status
        if started_at is not None:
            round_obj.started_at = started_at
        await self.state_mgr.update_status(self.game_id, status)

    async def _wait_until(self, deadline: datetime) -> None:
        while self._running:
            remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                return
            await asyncio.sleep(min(remaining, 0.25))

    async def open(self, round_obj: GameRound) -> None:
        config, house_edge_bp = await self._settings()
        timer_seconds, lock_before_end = round_timing_seconds(config)

        now = datetime.now(timezone.utc)
        lock_at = now + timedelta(seconds=timer_seconds - lock_before_end)
        result_at = now + timedelta(seconds=timer_seconds)
        payouts = config.get(
            "payout_multipliers",
            {"RED": 2, "GREEN": 2, "VIOLET": 4.5},
        )
        round_obj.status = GameRoundLifecycle.OPEN.value
        round_obj.started_at = now
        round_obj.result = {
            "betting_closes_at": lock_at.isoformat(),
            "result_at": result_at.isoformat(),
            "house_edge_bp": house_edge_bp,
            "payout_multipliers": payouts,
        }
        async with self.session_factory() as session:
            persisted = await RoundRepository(session).get_by_id(round_obj.id)
            persisted.status = GameRoundLifecycle.OPEN.value
            persisted.started_at = now
            persisted.result = round_obj.result
            await session.commit()

        await self.state_mgr.set_round_state(
            game_id=self.game_id,
            round_id=round_obj.id,
            round_no=round_obj.round_no,
            status=GameRoundLifecycle.OPEN.value,
            server_seed_hash=round_obj.server_seed_hash,
            started_at=now,
            metadata={
                "betting_closes_at": lock_at.isoformat(),
                "result_at": result_at.isoformat(),
            },
        )
        await self.publish_event(
            "round_open",
            {
                "round_no": round_obj.round_no,
                "server_seed_hash": round_obj.server_seed_hash,
                "opened_at": now.isoformat(),
                "betting_closes_at": lock_at.isoformat(),
                "result_at": result_at.isoformat(),
            },
            round_id=round_obj.id,
        )
        await self._wait_until(lock_at)

    async def lock(self, round_obj: GameRound) -> None:
        await self._set_status(round_obj, GameRoundLifecycle.LOCKED.value)
        await self._wait_until(datetime.fromisoformat(round_obj.result["result_at"]))

    async def resolve(self, round_obj: GameRound) -> Dict[str, Any]:
        parameters = round_obj.result or {}
        result = compute_colour(
            server_seed=round_obj.server_seed or "",
            client_seed=round_obj.client_seed or round_obj.id,
            nonce=round_obj.round_no,
            payout_multipliers=parameters.get("payout_multipliers"),
        )
        outcome = {
            "winning_colour": result.colour.value,
            "slot": result.slot,
            "payout_x100": result.payout_x100,
            "payout_multipliers": parameters.get("payout_multipliers"),
            "house_edge_bp": parameters.get("house_edge_bp"),
        }
        await self._set_status(round_obj, GameRoundLifecycle.RESULT.value)
        await self.publish_event(
            "result",
            {
                **outcome,
                "server_seed": round_obj.server_seed,
                "server_seed_hash": round_obj.server_seed_hash,
                "client_seed": round_obj.client_seed,
            },
            round_id=round_obj.id,
        )
        return outcome

    async def settle(self, round_obj: GameRound, outcome: Dict[str, Any]) -> None:
        winning_colour = outcome["winning_colour"]
        payout_x100 = outcome["payout_x100"]

        def evaluate_entry(entry: GameEntry):
            if (entry.selection or {}).get("colour") == winning_colour:
                payout = entry.bet_amount * payout_x100 // 100
                return True, payout_x100, payout
            return False, 0, 0

        await self.settlement_mgr.settle_round(
            round_id=round_obj.id,
            evaluate_entry_fn=evaluate_entry,
            outcome=outcome,
        )
        await self._set_status(round_obj, GameRoundLifecycle.SETTLED.value)

    async def history(self, round_obj: GameRound, outcome: Dict[str, Any]) -> None:
        async with self.session_factory() as session:
            repository = RoundRepository(session)
            await repository.complete_round(
                round_obj.id,
                round_obj.server_seed or "",
                outcome,
            )
            persisted = await repository.get_by_id(round_obj.id)
            persisted.status = GameRoundLifecycle.HISTORY.value
            await session.commit()
            result = persisted.game_result
            settled = {
                **outcome,
                "total_bets": result.total_bets if result else 0,
                "total_payouts": result.total_payouts if result else 0,
                "server_seed": round_obj.server_seed,
            }
        await self.state_mgr.clear_round_state(self.game_id)
        await self.publish_event("round_settled", settled, round_id=round_obj.id)
        round_obj.status = GameRoundLifecycle.HISTORY.value

    async def run_round_cycle(self) -> None:
        round_obj = await self.prepare_next_round(GameRoundLifecycle.CREATED.value)
        await self.open(round_obj)
        await self.lock(round_obj)
        outcome = await self.resolve(round_obj)
        await self.settle(round_obj, outcome)
        await self.history(round_obj, outcome)
        await asyncio.sleep(self.intermission_duration)
