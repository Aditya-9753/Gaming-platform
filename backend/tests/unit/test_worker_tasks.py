"""Focused tests for Celery worker database tasks."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.game import Game, GameEntry, GameRound
from app.models.game_archive import GameArchive
from app.models.notification import Notification
from app.models.role import Role
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.workers import tasks_archive, tasks_reconcile


@pytest.fixture
async def worker_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _make_user(session: AsyncSession, role: Role, name: str) -> User:
    user = User(
        id=str(uuid.uuid4()),
        username=f"{name}_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        password_hash="unused",
        role_id=role.id,
        is_active=True,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_reconcile_compares_completed_ledger_and_notifies_admins(
    worker_session_factory, monkeypatch
):
    async with worker_session_factory() as session:
        admin_role = Role(name="ADMIN")
        player_role = Role(name="USER")
        session.add_all([admin_role, player_role])
        await session.flush()
        admin = await _make_user(session, admin_role, "admin")
        player = await _make_user(session, player_role, "player")
        balanced = Wallet(user_id=admin.id, balance=1500, locked_balance=0)
        mismatched = Wallet(user_id=player.id, balance=900, locked_balance=0)
        session.add_all([balanced, mismatched])
        await session.flush()
        session.add_all(
            [
                WalletTransaction(
                    wallet_id=balanced.id,
                    idempotency_key="completed-balanced",
                    type="BONUS",
                    amount=1000,
                    balance_before=500,
                    balance_after=1500,
                    status="COMPLETED",
                ),
                WalletTransaction(
                    wallet_id=balanced.id,
                    idempotency_key="pending-ignored",
                    type="BONUS",
                    amount=900,
                    balance_before=1500,
                    balance_after=2400,
                    status="PENDING",
                ),
                WalletTransaction(
                    wallet_id=mismatched.id,
                    idempotency_key="mismatch-ledger",
                    type="BONUS",
                    amount=700,
                    balance_before=0,
                    balance_after=700,
                    status="COMPLETED",
                ),
            ]
        )
        await session.commit()

    monkeypatch.setattr(
        tasks_reconcile, "get_session_factory", lambda: worker_session_factory
    )
    result = await tasks_reconcile._reconcile_all_wallets()

    assert result == {"checked": 2, "mismatches": 1}
    async with worker_session_factory() as session:
        notifications = (
            await session.execute(
                select(Notification).where(Notification.user_id == admin.id)
            )
        ).scalars().all()
        assert len(notifications) == 1
        assert notifications[0].type == "ALERT"
        assert "1 wallet balance mismatch" in notifications[0].message
        assert mismatched.id in notifications[0].message
        assert (
            await session.execute(
                select(func.count(Notification.id)).where(
                    Notification.user_id == player.id
                )
            )
        ).scalar_one() == 0


@pytest.mark.asyncio
async def test_reconcile_does_not_notify_when_ledger_balances_match(
    worker_session_factory, monkeypatch
):
    async with worker_session_factory() as session:
        player_role = Role(name="USER")
        session.add(player_role)
        await session.flush()
        player = await _make_user(session, player_role, "balanced")
        wallet = Wallet(user_id=player.id, balance=1200, locked_balance=0)
        session.add(wallet)
        await session.flush()
        session.add(
            WalletTransaction(
                wallet_id=wallet.id,
                idempotency_key="balanced-ledger",
                type="BONUS",
                amount=1200,
                balance_before=0,
                balance_after=1200,
                status="COMPLETED",
            )
        )
        await session.commit()

    monkeypatch.setattr(
        tasks_reconcile, "get_session_factory", lambda: worker_session_factory
    )
    assert await tasks_reconcile._reconcile_all_wallets() == {
        "checked": 1,
        "mismatches": 0,
    }
    async with worker_session_factory() as session:
        assert (
            await session.execute(select(func.count(Notification.id)))
        ).scalar_one() == 0


@pytest.mark.asyncio
async def test_archive_moves_old_terminal_entries_and_rounds_to_archive(
    worker_session_factory, monkeypatch
):
    old_date = datetime.now(timezone.utc) - timedelta(days=100)
    async with worker_session_factory() as session:
        role = Role(name="USER")
        session.add(role)
        await session.flush()
        player = await _make_user(session, role, "archive")
        game = Game(id="color", name="Color", type="COLOR")
        old_round = GameRound(
            id=str(uuid.uuid4()),
            game_id=game.id,
            round_no=1,
            status="HISTORY",
            server_seed_hash="hash",
            server_seed="revealed-seed",
            created_at=old_date,
        )
        current_round = GameRound(
            id=str(uuid.uuid4()),
            game_id=game.id,
            round_no=2,
            status="HISTORY",
            server_seed_hash="hash",
            created_at=datetime.now(timezone.utc),
        )
        session.add_all([game, old_round, current_round])
        await session.flush()
        old_entry = GameEntry(
            id=str(uuid.uuid4()),
            round_id=old_round.id,
            user_id=player.id,
            idempotency_key="old-entry",
            bet_amount=100,
            payout_amount=0,
            status="LOST",
            created_at=old_date,
        )
        new_entry = GameEntry(
            id=str(uuid.uuid4()),
            round_id=current_round.id,
            user_id=player.id,
            idempotency_key="new-entry",
            bet_amount=100,
            payout_amount=0,
            status="LOST",
        )
        session.add_all(
            [
                old_entry,
                new_entry,
            ]
        )
        await session.commit()

    monkeypatch.setattr(
        tasks_archive, "get_session_factory", lambda: worker_session_factory
    )
    assert await tasks_archive._archive_old_rounds() == 2

    async with worker_session_factory() as session:
        archives = (await session.execute(select(GameArchive))).scalars().all()
        assert {(archive.record_type, archive.source_id) for archive in archives} == {
            ("ENTRY", old_entry.id),
            ("ROUND", old_round.id),
        }
        archived_round = next(item for item in archives if item.record_type == "ROUND")
        assert archived_round.payload["server_seed"] == "revealed-seed"
        assert (
            await session.execute(
                select(func.count(GameRound.id)).where(GameRound.id == old_round.id)
            )
        ).scalar_one() == 0
        assert (
            await session.execute(
                select(func.count(GameEntry.id)).where(
                    GameEntry.id == new_entry.id
                )
            )
        ).scalar_one() == 1
