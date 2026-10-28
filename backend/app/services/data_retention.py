"""Keep the database small: delete history nobody needs.

The lobby bots (``app.games.simulated_players``) place real bets so the live feeds look
busy, and every bet writes a game entry plus two ledger rows. Left alone that is about
200k rows (~160 MB) a day, which filled the 1 GB database in three days. Their history is
useless after a few hours (reports already exclude bots), so this job deletes:

* settled bot bets older than ``BOT_HISTORY_HOURS``;
* bot ledger rows older than that, except each bot wallet's latest row (the nightly
  reconciliation compares a wallet's balance with its latest ``balance_after``);
* finished rounds older than ``ROUND_HISTORY_DAYS`` that no longer have any bet, i.e.
  rounds nobody real played (rounds with a real player's bet are kept for fairness checks);
* refresh tokens that expired more than a day ago.

Real players' bets and ledger rows are never touched. Runs hourly inside the API process
(``app.affiliate.jobs``), in batches so the live games keep their database connections.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import get_settings
from app.core.logging import get_logger
from app.games.simulated_players import BOT_NAMES
from app.models.game import GameEntry, GameRound
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction

logger = get_logger("data_retention")

BATCH = 5000
MAX_BATCHES = 40  # per table per run: at most 200k rows, the rest goes next hour
FINISHED_BETS = ("WON", "LOST", "REFUNDED", "COMPLETED", "CANCELLED", "VOID", "VOIDED", "ABANDONED", "SETTLED")
FINISHED_ROUNDS = ("COMPLETED", "CANCELLED", "HISTORY", "SETTLED")


def _bot_user_ids():
    # Bots have one of the fixed names and neither a phone nor an email (real players always have a phone)
    return select(User.id).where(User.username.in_(BOT_NAMES), User.phone.is_(None), User.email.is_(None))


async def _delete_in_batches(db: AsyncSession, model: Any, condition: Any) -> int:
    total = 0
    for _ in range(MAX_BATCHES):
        ids = select(model.id).where(condition).limit(BATCH)
        result = await db.execute(delete(model).where(model.id.in_(ids)).execution_options(synchronize_session=False))
        await db.commit()
        total += result.rowcount or 0
        if (result.rowcount or 0) < BATCH:
            break
    return total


async def prune(db: AsyncSession) -> Dict[str, int]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    bot_cutoff = now - timedelta(hours=settings.BOT_HISTORY_HOURS)
    round_cutoff = now - timedelta(days=settings.ROUND_HISTORY_DAYS)
    bots = _bot_user_ids()

    bets = await _delete_in_batches(db, GameEntry, and_(
        GameEntry.user_id.in_(bots), GameEntry.created_at < bot_cutoff, GameEntry.status.in_(FINISHED_BETS),
    ))

    newer = aliased(WalletTransaction)
    latest_of_wallet = (
        select(func.max(newer.created_at)).where(newer.wallet_id == WalletTransaction.wallet_id).scalar_subquery()
    )
    ledger = await _delete_in_batches(db, WalletTransaction, and_(
        WalletTransaction.wallet_id.in_(select(Wallet.id).where(Wallet.user_id.in_(bots))),
        WalletTransaction.created_at < bot_cutoff,
        WalletTransaction.created_at < latest_of_wallet,
    ))

    rounds = await _delete_in_batches(db, GameRound, and_(
        GameRound.created_at < round_cutoff,
        GameRound.status.in_(FINISHED_ROUNDS),
        ~select(GameEntry.id).where(GameEntry.round_id == GameRound.id).exists(),
    ))

    tokens = await _delete_in_batches(db, RefreshToken, RefreshToken.expires_at < now - timedelta(days=1))

    removed = {"bot_bets": bets, "bot_ledger_rows": ledger, "empty_rounds": rounds, "expired_tokens": tokens}
    if any(removed.values()):
        logger.info("Old data removed", **removed)
    return removed
