"""Settlement pipeline for game rounds and entries.

Enforces non-negotiable financial rules:
- Every payout/loss is processed through WalletService.
- Locked credits are moved to available (on win/refund) or permanently deducted (on loss).
- Deterministic idempotency keys for each settlement transaction.
- GameResult records total wagers and payouts.
- Processes entries in batches to handle high-concurrency rounds cleanly.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.constants import RoundStatus
from app.core.logging import get_logger
from app.models.game import GameEntry, GameResult, GameRound
from app.repositories.entry_repo import EntryRepository
from app.repositories.round_repo import RoundRepository
from app.services.wallet_service import WalletService

logger = get_logger("game_settlement")


class RoundSettlementManager:
    """Manages transactional settlement of wagers for completed or cancelled rounds."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        batch_size: int = 50,
    ) -> None:
        self.session_factory = session_factory
        self.batch_size = batch_size

    async def settle_entry(
        self,
        session: AsyncSession,
        entry: GameEntry,
        won: bool,
        multiplier_basis_points: int,
        payout_amount: int,
        round_id: str,
    ) -> None:
        """Settle a single game entry inside an active database transaction."""
        entry_repo = EntryRepository(session)
        wallet_svc = WalletService(session)

        action_type = "win" if won else "loss"
        idempotency_key = f"settle:{round_id}:{entry.id}:{action_type}"
        reference = f"round:{round_id}:entry:{entry.id}"

        if won:
            await wallet_svc.settle_win(
                user_id=entry.user_id,
                bet_amount_paise=entry.bet_amount,
                win_amount_paise=payout_amount - entry.bet_amount,
                reference=reference,
                idempotency_key=idempotency_key,
            )
            await entry_repo.update_settlement(
                entry_id=entry.id,
                status="WON",
                payout_amount=payout_amount,
                multiplier=multiplier_basis_points,
            )
        else:
            await wallet_svc.settle_loss(
                user_id=entry.user_id,
                bet_amount_paise=entry.bet_amount,
                reference=reference,
                idempotency_key=idempotency_key,
            )
            await entry_repo.update_settlement(
                entry_id=entry.id,
                status="LOST",
                payout_amount=0,
                multiplier=0,
            )

    async def settle_round(
        self,
        round_id: str,
        evaluate_entry_fn: Callable[[GameEntry], Tuple[bool, int, int]],
        outcome: Dict[str, Any],
    ) -> GameResult:
        """Settle all entries of a round in configurable batches and record aggregated GameResult."""
        total_bets = 0
        total_payouts = 0

        # 1. Fetch entries to settle
        async with self.session_factory() as session:
            entry_repo = EntryRepository(session)
            entries = await entry_repo.get_by_round_id(round_id)

        # 2. Process in batches
        for i in range(0, len(entries), self.batch_size):
            batch = entries[i : i + self.batch_size]
            async with self.session_factory() as session:
                for entry in batch:
                    total_bets += entry.bet_amount

                    if entry.status != "PLACED":
                        if entry.status == "WON":
                            total_payouts += entry.payout_amount
                        continue

                    won, mult_bp, payout = evaluate_entry_fn(entry)
                    try:
                        await self.settle_entry(
                            session=session,
                            entry=entry,
                            won=won,
                            multiplier_basis_points=mult_bp,
                            payout_amount=payout,
                            round_id=round_id,
                        )
                        if won:
                            total_payouts += payout
                    except Exception as exc:
                        logger.error(
                            "Error settling game entry in batch",
                            entry_id=entry.id,
                            user_id=entry.user_id,
                            error=str(exc),
                            exc_info=True,
                        )
                        raise
                await session.commit()

        # 3. Save aggregated round result
        async with self.session_factory() as session:
            round_repo = RoundRepository(session)
            res = await round_repo.save_round_result(
                round_id=round_id,
                outcome=outcome,
                total_bets=total_bets,
                total_payouts=total_payouts,
            )
            await session.commit()
            return res

    async def refund_round(self, round_id: str, reason: str = "ROUND_CANCELLED") -> None:
        """Refund all placed entries in a round that was cancelled or aborted."""
        async with self.session_factory() as session:
            entry_repo = EntryRepository(session)
            entries = await entry_repo.get_by_round_id(round_id)

        for i in range(0, len(entries), self.batch_size):
            batch = entries[i : i + self.batch_size]
            async with self.session_factory() as session:
                entry_repo = EntryRepository(session)
                wallet_svc = WalletService(session)

                for entry in batch:
                    if entry.status == "PLACED":
                        idempotency_key = f"refund:{round_id}:{entry.id}"
                        reference = f"refund:round:{round_id}:{reason}"
                        try:
                            await wallet_svc.refund(
                                user_id=entry.user_id,
                                amount_paise=entry.bet_amount,
                                reference=reference,
                                idempotency_key=idempotency_key,
                            )
                            await entry_repo.update_settlement(
                                entry_id=entry.id,
                                status="REFUNDED",
                                payout_amount=entry.bet_amount,
                                multiplier=100,
                            )
                        except Exception as exc:
                            logger.error(
                                "Failed to refund entry on round cancellation",
                                entry_id=entry.id,
                                error=str(exc),
                            )
                await session.commit()

        async with self.session_factory() as session:
            round_repo = RoundRepository(session)
            await round_repo.update_status(round_id, RoundStatus.CANCELLED.value)
            await session.commit()
