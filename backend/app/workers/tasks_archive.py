"""Data archiving background task."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.models.game import GameEntry, GameRound
from app.models.game_archive import GameArchive
from app.workers.celery_app import celery_app

logger = get_logger("worker_archive")

_TERMINAL_ROUND_STATUSES = ("COMPLETED", "CANCELLED", "HISTORY", "SETTLED")
_BATCH_SIZE = 1000


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _entry_payload(entry: GameEntry) -> dict:
    return {
        "id": entry.id,
        "round_id": entry.round_id,
        "user_id": entry.user_id,
        "idempotency_key": entry.idempotency_key,
        "bet_amount": entry.bet_amount,
        "multiplier": entry.multiplier,
        "payout_amount": entry.payout_amount,
        "status": entry.status,
        "selection": entry.selection,
        "created_at": _iso(entry.created_at),
        "updated_at": _iso(entry.updated_at),
    }


def _round_payload(round_: GameRound) -> dict:
    result = round_.game_result
    return {
        "id": round_.id,
        "game_id": round_.game_id,
        "round_no": round_.round_no,
        "status": round_.status,
        "server_seed_hash": round_.server_seed_hash,
        "server_seed": round_.server_seed,
        "client_seed": round_.client_seed,
        "result": round_.result,
        "started_at": _iso(round_.started_at),
        "ended_at": _iso(round_.ended_at),
        "created_at": _iso(round_.created_at),
        "game_result": (
            {
                "id": result.id,
                "outcome": result.outcome,
                "total_bets": result.total_bets,
                "total_payouts": result.total_payouts,
                "created_at": _iso(result.created_at),
            }
            if result
            else None
        ),
    }


async def _archive_old_rounds(days: int = 90) -> int:
    """Move old, terminal game entries and rounds to the archive table."""
    if days < 0:
        raise ValueError("Archive age must be non-negative")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    archived_at = datetime.now(timezone.utc)
    async with get_session_factory()() as session:
        entries = (
            await session.execute(
                select(GameEntry)
                .join(GameRound, GameRound.id == GameEntry.round_id)
                .where(
                    GameEntry.created_at < cutoff,
                    GameRound.status.in_(_TERMINAL_ROUND_STATUSES),
                )
                .order_by(GameEntry.created_at)
                .limit(_BATCH_SIZE)
            )
        ).scalars().all()
        for entry in entries:
            session.add(
                GameArchive(
                    record_type="ENTRY",
                    source_id=entry.id,
                    source_created_at=entry.created_at,
                    archived_at=archived_at,
                    payload=_entry_payload(entry),
                )
            )
            await session.delete(entry)
        await session.flush()

        old_rounds = (
            await session.execute(
                select(GameRound)
                .options(selectinload(GameRound.game_result))
                .where(
                    GameRound.created_at < cutoff,
                    GameRound.status.in_(_TERMINAL_ROUND_STATUSES),
                    ~select(GameEntry.id)
                    .where(GameEntry.round_id == GameRound.id)
                    .exists(),
                )
                .order_by(GameRound.created_at)
                .limit(_BATCH_SIZE)
            )
        ).scalars().all()
        for round_ in old_rounds:
            session.add(
                GameArchive(
                    record_type="ROUND",
                    source_id=round_.id,
                    source_created_at=round_.created_at,
                    archived_at=archived_at,
                    payload=_round_payload(round_),
                )
            )
            await session.delete(round_)

        await session.commit()
        return len(entries) + len(old_rounds)


@celery_app.task(name="app.workers.tasks_archive.archive_old_rounds_task")
def archive_old_rounds_task() -> int:
    """Periodically move old terminal rounds and entries to cold archival storage."""
    count = asyncio.run(_archive_old_rounds())
    logger.info("Checked rounds eligible for archival", count=count)
    return count
