"""Hourly clean-up: old bot history, empty rounds and expired tokens go; real players' data stays."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.game import Game, GameEntry, GameRound
from app.models.refresh_token import RefreshToken
from app.models.role import Role
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.services.data_retention import prune

NOW = datetime.now(timezone.utc)
OLD = NOW - timedelta(days=5)


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _user(uid: str, username: str, phone=None) -> User:
    return User(id=uid, username=username, phone=phone, email=None, password_hash="x", role_id=1, is_active=True)


def _round(no: int, created_at: datetime, status: str = "COMPLETED") -> GameRound:
    return GameRound(id=str(uuid.uuid4()), game_id="aviator", round_no=no, status=status,
                     server_seed_hash="h" * 64, created_at=created_at)


def _bet(user_id: str, round_id: str, created_at: datetime, status: str = "LOST") -> GameEntry:
    return GameEntry(id=str(uuid.uuid4()), round_id=round_id, user_id=user_id, idempotency_key=uuid.uuid4().hex,
                     bet_amount=1000, payout_amount=0, status=status, created_at=created_at)


def _tx(wallet_id: str, created_at: datetime, balance_after: int) -> WalletTransaction:
    return WalletTransaction(id=str(uuid.uuid4()), wallet_id=wallet_id, idempotency_key=uuid.uuid4().hex, type="BET",
                             amount=1000, balance_before=balance_after + 1000, balance_after=balance_after,
                             status="COMPLETED", created_at=created_at)


async def _count(db: AsyncSession, model, *where) -> int:
    return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar_one()


async def test_prune_removes_only_useless_history(db):
    db.add(Role(id=1, name="USER"))
    db.add(Game(id="aviator", name="Aviator", type="CRASH", is_active=True))
    db.add_all([_user("bot", "Rahul_King"), _user("real", "9876543210", phone="+919876543210")])
    db.add_all([Wallet(id="w-bot", user_id="bot", balance=5000, locked_balance=0, currency="VIRTUAL"),
                Wallet(id="w-real", user_id="real", balance=7000, locked_balance=0, currency="VIRTUAL")])
    bot_round_old, real_round_old, empty_old, empty_new, open_old = (
        _round(1, OLD), _round(2, OLD), _round(3, OLD), _round(4, NOW), _round(5, OLD, status="RUNNING"))
    db.add_all([bot_round_old, real_round_old, empty_old, empty_new, open_old])
    db.add_all([
        _bet("bot", bot_round_old.id, OLD),                       # old settled bot bet -> deleted
        _bet("bot", open_old.id, OLD, status="PLACED"),           # bet still open -> kept
        _bet("bot", empty_new.id, NOW),                           # recent bot bet -> kept
        _bet("real", real_round_old.id, OLD),                     # real player's bet -> kept forever
    ])
    db.add_all([
        _tx("w-bot", OLD - timedelta(hours=2), 9000),              # old bot ledger rows -> deleted
        _tx("w-bot", OLD - timedelta(hours=1), 7000),
        _tx("w-bot", OLD, 5000),                                   # bot wallet's latest row -> kept (reconciliation)
        _tx("w-real", OLD, 7000),                                  # real ledger -> kept
    ])
    db.add_all([
        RefreshToken(id=str(uuid.uuid4()), user_id="real", family_id="f", token_hash="a" * 64, expires_at=NOW - timedelta(days=3)),
        RefreshToken(id=str(uuid.uuid4()), user_id="real", family_id="f", token_hash="b" * 64, expires_at=NOW + timedelta(days=3)),
    ])
    await db.commit()

    removed = await prune(db)

    assert removed == {"bot_bets": 1, "bot_ledger_rows": 2, "empty_rounds": 2, "expired_tokens": 1}
    assert await _count(db, GameEntry, GameEntry.user_id == "real") == 1
    assert await _count(db, GameEntry, GameEntry.user_id == "bot") == 2
    assert await _count(db, WalletTransaction, WalletTransaction.wallet_id == "w-real") == 1
    latest = (await db.execute(select(WalletTransaction.balance_after).where(WalletTransaction.wallet_id == "w-bot"))).scalars().all()
    assert latest == [5000]  # still equals the wallet balance
    kept_rounds = set((await db.execute(select(GameRound.round_no))).scalars())
    assert kept_rounds == {2, 4, 5}  # real player's round, recent round, open round; old empty ones (1 after its bet went, 3) gone
    assert await _count(db, RefreshToken) == 1

    assert await prune(db) == {"bot_bets": 0, "bot_ledger_rows": 0, "empty_rounds": 0, "expired_tokens": 0}
