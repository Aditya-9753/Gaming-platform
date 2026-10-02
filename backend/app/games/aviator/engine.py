"""Aviator round lifecycle and server-authoritative crash execution."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.constants import GameRoundLifecycle, RoundStatus
from app.core.logging import get_logger
from app.games.aviator.rules import (
    DEFAULT_EXP_GROWTH_RATE,
    GROWTH_MODEL_EXPONENTIAL,
    GROWTH_MODEL_POWER,
    compute_crash_point,
    crash_elapsed_seconds,
    crash_x100_to_float,
    elapsed_since,
    multiplier_x100_at,
)
from app.games.aviator.service import AviatorService
from app.games.base.engine import BaseGameEngine
from app.games.base.registry import register_game
from app.models.game import GameEntry, GameRound
from app.repositories.entry_repo import EntryRepository
from app.repositories.game_repo import GameRepository
from app.repositories.round_repo import RoundRepository

logger = get_logger("aviator_engine")


@register_game("aviator")
class AviatorEngine(BaseGameEngine):
    """Run crash rounds without broadcasting continuous multiplier ticks."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis,
        betting_duration_sec: float = 6.0,
        intermission_duration_sec: float = 3.0,
        tick_interval_sec: float = 0.05,
    ) -> None:
        super().__init__(
            game_id="aviator",
            session_factory=session_factory,
            redis=redis,
            betting_duration_sec=betting_duration_sec,
            intermission_duration_sec=intermission_duration_sec,
        )
        self.tick_interval = tick_interval_sec

    async def _configuration(self) -> tuple[dict, int]:
        async with self.session_factory() as session:
            settings = await GameRepository(session).get_settings("aviator")
            if not settings:
                raise ValueError("Aviator game settings are not configured")
            return settings.config or {}, settings.house_edge_percent

    async def _set_round_status(
        self, round_obj: GameRound, status: str, started_at: datetime | None = None
    ) -> None:
        async with self.session_factory() as session:
            repository = RoundRepository(session)
            await repository.update_status(round_obj.id, status, started_at=started_at)
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
        config, house_edge_bp = await self._configuration()
        duration = float(config.get("betting_duration_sec", self.betting_duration))
        growth_model = str(config.get("growth_model", GROWTH_MODEL_EXPONENTIAL))
        if growth_model == GROWTH_MODEL_EXPONENTIAL:
            growth_rate = float(config.get("exp_growth_rate", DEFAULT_EXP_GROWTH_RATE))
            growth_power = 1.0
            formula = "e ** (elapsed_seconds * rate)"
        else:
            growth_model = GROWTH_MODEL_POWER
            growth_rate = float(config.get("growth_rate", 0.08))
            growth_power = float(config.get("growth_power", 1.3))
            formula = "1 + (elapsed_seconds * rate) ** power"
        if duration <= 0 or growth_rate <= 0 or growth_power <= 0:
            raise ValueError("Aviator timing and growth settings must be positive")

        now = datetime.now(timezone.utc)
        start_at = now + timedelta(seconds=duration)
        round_obj.result = {
            "betting_closes_at": start_at.isoformat(),
            "growth_rate": growth_rate,
            "growth_power": growth_power,
            "growth_model": growth_model,
            "house_edge_bp": house_edge_bp,
        }
        round_obj.status = GameRoundLifecycle.BETTING_OPEN.value
        async with self.session_factory() as session:
            persisted = await RoundRepository(session).get_by_id(round_obj.id)
            persisted.status = GameRoundLifecycle.BETTING_OPEN.value
            persisted.started_at = None
            persisted.result = round_obj.result
            await session.commit()
        round_obj.started_at = None

        await self.state_mgr.set_round_state(
            game_id=self.game_id,
            round_id=round_obj.id,
            round_no=round_obj.round_no,
            status=GameRoundLifecycle.BETTING_OPEN.value,
            server_seed_hash=round_obj.server_seed_hash,
            started_at=now,
            metadata={
                "round_start_ts": start_at.isoformat(),
                "growth_parameters": {
                    "rate": growth_rate,
                    "power": growth_power,
                    "model": growth_model,
                },
            },
        )
        await self.publish_event(
            "round_open",
            {
                "round_no": round_obj.round_no,
                "server_seed_hash": round_obj.server_seed_hash,
                "round_start_ts": start_at.isoformat(),
                "growth_parameters": {
                    "rate": growth_rate,
                    "power": growth_power,
                    "model": growth_model,
                    "formula": formula,
                },
            },
            round_id=round_obj.id,
        )
        await self._wait_until(start_at)

    async def lock(self, round_obj: GameRound) -> None:
        started_at = datetime.fromisoformat(round_obj.result["betting_closes_at"])
        await self._set_round_status(round_obj, RoundStatus.RUNNING.value, started_at)

    async def resolve(self, round_obj: GameRound) -> Dict[str, Any]:
        parameters = round_obj.result or {}
        growth_rate = float(parameters["growth_rate"])
        growth_power = float(parameters["growth_power"])
        growth_model = str(parameters.get("growth_model", GROWTH_MODEL_POWER))
        house_edge_bp = int(parameters["house_edge_bp"])
        crash_x100 = compute_crash_point(
            round_obj.server_seed or "",
            round_obj.client_seed or round_obj.id,
            round_obj.round_no,
            house_edge_bp,
        )
        crash_at = crash_elapsed_seconds(crash_x100, growth_rate, growth_power, growth_model)
        # Betting is closed, so the set of auto-cashout targets is fixed: load once
        # instead of querying the database on every 50 ms tick.
        pending = await self._auto_cashout_targets(round_obj.id)
        while self._running and round_obj.started_at:
            elapsed = elapsed_since(round_obj.started_at, datetime.now(timezone.utc))
            current_x100 = min(
                multiplier_x100_at(elapsed, growth_rate, growth_power, growth_model),
                crash_x100,
            )
            pending = await self._process_auto_cashouts(round_obj.id, current_x100, pending)
            if elapsed >= crash_at:
                break
            await asyncio.sleep(min(self.tick_interval, max(0.001, crash_at - elapsed)))

        outcome = {
            "crash_point_x100": crash_x100,
            "crash_point": crash_x100_to_float(crash_x100),
            "house_edge_bp": house_edge_bp,
        }
        await self._set_round_status(round_obj, GameRoundLifecycle.CRASHED.value)
        await self.publish_event(
            "crash",
            {
                **outcome,
                "server_seed": round_obj.server_seed,
                "server_seed_hash": round_obj.server_seed_hash,
                "client_seed": round_obj.client_seed,
            },
            round_id=round_obj.id,
        )
        return outcome

    async def _auto_cashout_targets(self, round_id: str) -> list[tuple[int, str, str]]:
        """(target_x100, entry_id, user_id) for open bets with auto cash-out, lowest first."""
        async with self.session_factory() as session:
            entries = await EntryRepository(session).get_by_round_id(round_id)
        targets = []
        for entry in entries:
            target = (entry.selection or {}).get("auto_cashout")
            if entry.status == "PLACED" and target is not None:
                targets.append((int(round(float(target) * 100)), entry.id, entry.user_id))
        return sorted(targets)

    async def _process_auto_cashouts(
        self, round_id: str, multiplier_x100: int, pending: list[tuple[int, str, str]]
    ) -> list[tuple[int, str, str]]:
        """Cash out every pending target reached at this multiplier; returns the rest."""
        while pending and pending[0][0] <= multiplier_x100:
            _target, entry_id, user_id = pending.pop(0)
            try:
                async with self.session_factory() as session:
                    await AviatorService(session, redis=self.redis).cashout(
                        user_id=user_id,
                        round_id=round_id,
                        entry_id=entry_id,
                        idempotency_key=f"aviator:auto:{round_id}:{entry_id}",
                        automatic=True,
                    )
            except Exception as exc:
                # Already cashed out manually / voided: never let one bet stop the round
                logger.info("Auto cash-out skipped", entry_id=entry_id, reason=str(exc))
        return pending

    async def settle(self, round_obj: GameRound, outcome: Dict[str, Any]) -> None:
        await self._set_round_status(round_obj, GameRoundLifecycle.SETTLING.value)

        def evaluate_loss(entry: GameEntry):
            return False, 0, 0

        await self.settlement_mgr.settle_round(
            round_id=round_obj.id,
            evaluate_entry_fn=evaluate_loss,
            outcome=outcome,
        )

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
        round_obj = await self.prepare_next_round(GameRoundLifecycle.WAITING.value)
        await self.open(round_obj)
        await self.lock(round_obj)
        outcome = await self.resolve(round_obj)
        await self.settle(round_obj, outcome)
        await self.history(round_obj, outcome)
        await asyncio.sleep(self.intermission_duration)
