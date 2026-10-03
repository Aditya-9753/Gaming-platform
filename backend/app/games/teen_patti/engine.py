"""Teen Patti round lifecycle: bet (20s) -> lock -> deal & reveal -> settle."""

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
from app.games.teen_patti.rules import (
    BETTING_SECONDS,
    GAME_ID,
    REVEAL_SECONDS,
    TIE,
    compute_outcome,
    payout_from_config,
)
from app.models.game import GameEntry, GameRound
from app.repositories.game_repo import GameRepository
from app.repositories.round_repo import RoundRepository

logger = get_logger("teen_patti_engine")


@register_game(GAME_ID)
class TeenPattiEngine(BaseGameEngine):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], redis: Redis) -> None:
        super().__init__(
            game_id=GAME_ID,
            session_factory=session_factory,
            redis=redis,
            betting_duration_sec=float(BETTING_SECONDS),
            intermission_duration_sec=3.0,
        )

    async def _payout(self) -> int:
        async with self.session_factory() as session:
            settings = await GameRepository(session).get_settings(self.game_id)
            return payout_from_config(settings.config if settings else None)

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

    async def open(self, round_obj: GameRound) -> None:
        payout = await self._payout()
        now = datetime.now(timezone.utc)
        lock_at = now + timedelta(seconds=BETTING_SECONDS)
        result_at = lock_at + timedelta(seconds=2)
        round_obj.status = GameRoundLifecycle.OPEN.value
        round_obj.started_at = now
        round_obj.result = {
            "betting_closes_at": lock_at.isoformat(),
            "result_at": result_at.isoformat(),
            "payout_x100": payout,
        }
        async with self.session_factory() as session:
            persisted = await RoundRepository(session).get_by_id(round_obj.id)
            persisted.status = GameRoundLifecycle.OPEN.value
            persisted.started_at = now
            persisted.result = round_obj.result
            await session.commit()

        meta = {"betting_closes_at": lock_at.isoformat(), "result_at": result_at.isoformat(), "payout_x100": payout}
        await self.state_mgr.set_round_state(
            game_id=self.game_id,
            round_id=round_obj.id,
            round_no=round_obj.round_no,
            status=GameRoundLifecycle.OPEN.value,
            server_seed_hash=round_obj.server_seed_hash,
            started_at=now,
            metadata=meta,
        )
        await self.publish_event(
            "round_open",
            {
                "round_no": round_obj.round_no,
                "server_seed_hash": round_obj.server_seed_hash,
                "client_seed": round_obj.client_seed or round_obj.id,
                "nonce": round_obj.round_no,
                **meta,
            },
            round_id=round_obj.id,
        )
        await self._wait_until(lock_at)

    async def lock(self, round_obj: GameRound) -> None:
        await self._set_status(round_obj, GameRoundLifecycle.LOCKED.value)
        await self.publish_event("round_locked", {"round_no": round_obj.round_no}, round_id=round_obj.id)
        await self._wait_until(datetime.fromisoformat(round_obj.result["result_at"]))

    async def resolve(self, round_obj: GameRound) -> Dict[str, Any]:
        outcome = compute_outcome(
            round_obj.server_seed or "",
            round_obj.client_seed or round_obj.id,
            round_obj.round_no,
        )
        result = {
            **outcome._asdict(),
            "payout_x100": round_obj.result.get("payout_x100"),
        }
        await self._set_status(round_obj, GameRoundLifecycle.RESULT.value)
        await self.publish_event(
            "result",
            {
                **result,
                "round_no": round_obj.round_no,
                "server_seed": round_obj.server_seed,
                "server_seed_hash": round_obj.server_seed_hash,
                "client_seed": round_obj.client_seed,
            },
            round_id=round_obj.id,
        )
        # Let players watch the cards flip before the round is settled
        await asyncio.sleep(REVEAL_SECONDS)
        return result

    async def settle(self, round_obj: GameRound, outcome: Dict[str, Any]) -> None:
        winner = outcome["winner"]
        payout = int(outcome.get("payout_x100") or payout_from_config(None))

        def evaluate_entry(entry: GameEntry):
            side = (entry.selection or {}).get("value")
            if winner == TIE:
                return True, 100, entry.bet_amount  # tie: stake refunded
            if side == winner:
                return True, payout, entry.bet_amount * payout // 100
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
