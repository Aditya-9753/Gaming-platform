"""WinGo round lifecycle: clock-aligned periods for 30s / 1m / 3m / 5m modes."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.constants import GameRoundLifecycle
from app.core.logging import get_logger
from app.games.base.engine import BaseGameEngine
from app.games.base.registry import register_game
from app.games.wingo.rules import (
    MODES,
    compute_outcome,
    payout_x100,
    payouts_from_config,
)
from app.models.game import GameEntry, GameRound
from app.repositories.game_repo import GameRepository
from app.repositories.round_repo import RoundRepository

logger = get_logger("wingo_engine")

# Periods are numbered on the Indian calendar day, like popular WinGo sites.
_IST = timezone(timedelta(hours=5, minutes=30))


def period_for(result_at: datetime, duration: int, mode_code: int) -> str:
    """e.g. 2026100210001267 = date + mode code + sequence of the day."""
    local = result_at.astimezone(_IST)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    sequence = int((local - midnight).total_seconds() // duration)
    return f"{local:%Y%m%d}{mode_code}{sequence:05d}"


class WingoEngine(BaseGameEngine):
    """One engine instance per mode (game_id)."""

    def __init__(
        self,
        game_id: str,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis,
    ) -> None:
        duration, lock, _label, code = MODES[game_id]
        super().__init__(
            game_id=game_id,
            session_factory=session_factory,
            redis=redis,
            betting_duration_sec=float(duration - lock),
            intermission_duration_sec=0.2,
        )
        self.duration = duration
        self.lock_seconds = lock
        self.mode_code = code

    async def _payouts(self) -> Dict[str, int]:
        async with self.session_factory() as session:
            settings = await GameRepository(session).get_settings(self.game_id)
            return payouts_from_config(settings.config if settings else None)

    async def _set_status(self, round_obj: GameRound, status: str) -> None:
        async with self.session_factory() as session:
            await RoundRepository(session).update_status(round_obj.id, status)
            await session.commit()
        round_obj.status = status
        await self.state_mgr.update_status(self.game_id, status)

    async def _wait_until(self, deadline: datetime) -> None:
        while self._running:
            remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                return
            await asyncio.sleep(min(remaining, 0.25))

    def _next_draw(self, now: datetime) -> datetime:
        epoch = now.timestamp()
        draw = math.ceil(epoch / self.duration) * self.duration
        # Too little time left to bet: skip to the following period
        if draw - epoch < self.lock_seconds + 2:
            draw += self.duration
        return datetime.fromtimestamp(draw, tz=timezone.utc)

    async def open(self, round_obj: GameRound) -> None:
        payouts = await self._payouts()
        now = datetime.now(timezone.utc)
        result_at = self._next_draw(now)
        lock_at = result_at - timedelta(seconds=self.lock_seconds)
        period = period_for(result_at, self.duration, self.mode_code)
        round_obj.status = GameRoundLifecycle.OPEN.value
        round_obj.started_at = now
        round_obj.result = {
            "period": period,
            "mode": self.game_id,
            "duration": self.duration,
            "betting_closes_at": lock_at.isoformat(),
            "result_at": result_at.isoformat(),
            "payouts_x100": payouts,
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
                "period": period,
                "betting_closes_at": lock_at.isoformat(),
                "result_at": result_at.isoformat(),
            },
        )
        await self.publish_event(
            "round_open",
            {
                "round_no": round_obj.round_no,
                "period": period,
                "server_seed_hash": round_obj.server_seed_hash,
                "betting_closes_at": lock_at.isoformat(),
                "result_at": result_at.isoformat(),
            },
            round_id=round_obj.id,
        )
        await self._wait_until(lock_at)

    async def lock(self, round_obj: GameRound) -> None:
        await self._set_status(round_obj, GameRoundLifecycle.LOCKED.value)
        await self.publish_event("round_locked", {"period": round_obj.result["period"]}, round_id=round_obj.id)
        await self._wait_until(datetime.fromisoformat(round_obj.result["result_at"]))

    async def resolve(self, round_obj: GameRound) -> Dict[str, Any]:
        outcome = compute_outcome(
            round_obj.server_seed or "",
            round_obj.client_seed or round_obj.id,
            round_obj.round_no,
        )
        result = {
            "period": round_obj.result["period"],
            "number": outcome.number,
            "colours": list(outcome.colours),
            "size": outcome.size,
            "payouts_x100": round_obj.result.get("payouts_x100"),
        }
        await self._set_status(round_obj, GameRoundLifecycle.RESULT.value)
        await self.publish_event(
            "result",
            {
                **result,
                "server_seed": round_obj.server_seed,
                "server_seed_hash": round_obj.server_seed_hash,
                "client_seed": round_obj.client_seed,
            },
            round_id=round_obj.id,
        )
        return result

    async def settle(self, round_obj: GameRound, outcome: Dict[str, Any]) -> None:
        from app.games.wingo.rules import WingoOutcome

        drawn = WingoOutcome(outcome["number"], tuple(outcome["colours"]), outcome["size"])
        payouts = outcome.get("payouts_x100") or payouts_from_config(None)

        def evaluate_entry(entry: GameEntry):
            selection = entry.selection or {}
            multiplier = payout_x100(selection.get("type", ""), selection.get("value", ""), drawn, payouts)
            if multiplier:
                return True, multiplier, entry.bet_amount * multiplier // 100
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
            await repository.complete_round(round_obj.id, round_obj.server_seed or "", outcome)
            persisted = await repository.get_by_id(round_obj.id)
            persisted.status = GameRoundLifecycle.HISTORY.value
            await session.commit()
            result = persisted.game_result
            settled = {
                **outcome,
                "total_bets": result.total_bets if result else 0,
                "total_payouts": result.total_payouts if result else 0,
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


def _make_mode_engine(game_id: str) -> type:
    def __init__(self, session_factory, redis):  # noqa: N807
        WingoEngine.__init__(self, game_id, session_factory, redis)

    cls = type(f"WingoEngine_{game_id}", (WingoEngine,), {"__init__": __init__})
    return register_game(game_id)(cls)


MODE_ENGINES = {game_id: _make_mode_engine(game_id) for game_id in MODES}
