"""Cricket ball-by-ball game engine."""

from __future__ import annotations

import asyncio
from typing import Any, Dict
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.games.base.engine import BaseGameEngine
from app.games.cricket.rules import compute_ball_outcome
from app.models.game import GameEntry, GameRound

logger = get_logger("cricket_engine")


class CricketEngine(BaseGameEngine):
    """Real-time engine running continuous Cricket ball delivery rounds."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis,
        betting_duration_sec: float = 10.0,
        intermission_duration_sec: float = 3.0,
    ) -> None:
        super().__init__(
            game_id="cricket",
            session_factory=session_factory,
            redis=redis,
            betting_duration_sec=betting_duration_sec,
            intermission_duration_sec=intermission_duration_sec,
        )

    async def resolve(self, round_obj: GameRound) -> Dict[str, Any]:
        """Compute provably fair ball outcome (Dot, Single, Boundary, Wicket, etc.)."""
        # Bowler delivery flight delay
        await asyncio.sleep(2.0)

        client_seed = round_obj.client_seed or "cricket_public_client"
        delivery = compute_ball_outcome(
            server_seed=round_obj.server_seed or "default_seed",
            client_seed=client_seed,
            nonce=round_obj.round_no,
        )

        return {
            "outcome": delivery.outcome_type.value,
            "runs": delivery.runs,
            "is_wicket": delivery.is_wicket,
            "payout_bp": delivery.payout_bp,
            "slot": delivery.slot,
        }

    async def settle(self, round_obj: GameRound, outcome: Dict[str, Any]) -> None:
        """Settle delivery predictions matching the result in batches."""
        target_outcome = outcome["outcome"]
        payout_bp = outcome["payout_bp"]

        def evaluate_entry(entry: GameEntry):
            pred = (entry.selection or {}).get("prediction")
            if pred == target_outcome:
                payout = int(entry.bet_amount * (payout_bp / 100.0))
                return True, payout_bp, payout
            return False, 0, 0

        await self.settlement_mgr.settle_round(
            round_id=round_obj.id,
            evaluate_entry_fn=evaluate_entry,
            outcome=outcome,
        )
