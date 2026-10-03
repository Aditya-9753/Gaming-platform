from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.constants import GameRoundLifecycle
from app.core.database import Base
from app.core.exceptions import BadRequestException
from app.games.teen_patti.engine import TeenPattiEngine
from app.games.teen_patti.rules import compute_outcome, hand_key, normalise_side
from app.games.teen_patti.service import TeenPattiBetRequest, TeenPattiService
from app.models.game import Game, GameEntry, GameRound, GameSetting
from app.models.role import Role
from app.models.user import User
from app.models.wallet import Wallet


def test_hand_ranking_order():
    order = [
        ["2S", "2H", "2D"],  # trail
        ["5H", "6H", "7H"],  # pure sequence
        ["AS", "KH", "QD"],  # A-K-Q sequence (best)
        ["AS", "2H", "3D"],  # A-2-3 (second best)
        ["KS", "QH", "JD"],
        ["5H", "6S", "7H"],
        ["2H", "9H", "KH"],  # color
        ["9S", "9H", "AD"],  # pair
        ["AS", "9H", "4D"],  # high card
    ]
    keys = [hand_key(h) for h in order]
    assert keys == sorted(keys, reverse=True)
    assert hand_key(["9S", "9H", "AD"]) > hand_key(["9C", "9D", "KD"])  # kicker
    assert hand_key(["AS", "9H", "4D"]) == hand_key(["AH", "9D", "4C"])  # suits never matter


def test_outcome_is_deterministic_and_uses_six_distinct_cards():
    one = compute_outcome("server", "client", 7)
    assert one == compute_outcome("server", "client", 7)
    assert len(set(one.player_a + one.player_b)) == 6
    assert one.winner in ("A", "B", "TIE")


def test_side_validation():
    assert normalise_side(" a ") == "A"
    with pytest.raises(ValueError):
        normalise_side("C")


async def _setup(session_factory, balance=10_000):
    user_id = str(uuid.uuid4())
    async with session_factory() as session:
        role = Role(name=f"TEST_{uuid.uuid4().hex[:8]}", description="test role")
        session.add(role)
        await session.flush()
        if await session.get(Game, "teen_patti") is None:
            session.add(Game(id="teen_patti", name="Teen Patti", type="CARD", is_active=True))
            await session.flush()
            session.add(GameSetting(game_id="teen_patti", min_bet=100, max_bet=500_000, house_edge_percent=200, config={"payout": 1.96}))
        session.add(User(id=user_id, username=f"u_{uuid.uuid4().hex[:8]}", password_hash="x", role_id=role.id, is_active=True, is_verified=True))
        await session.flush()
        session.add(Wallet(id=str(uuid.uuid4()), user_id=user_id, balance=balance, locked_balance=0, currency="VIRTUAL", is_frozen=False))
        await session.commit()
    return user_id


async def _open_round(session_factory, closes_in=10):
    round_id = str(uuid.uuid4())
    async with session_factory() as session:
        session.add(GameRound(
            id=round_id, game_id="teen_patti", round_no=1, status=GameRoundLifecycle.OPEN.value,
            server_seed_hash="a" * 64, server_seed="seed", client_seed="client",
            result={"betting_closes_at": (datetime.now(timezone.utc) + timedelta(seconds=closes_in)).isoformat(), "payout_x100": 196},
        ))
        await session.commit()
    return round_id


@pytest.mark.asyncio
@pytest.mark.parametrize("winner, side, expected_balance, expected_status", [
    ("A", "A", 10_000 - 1_000 + 1_960, "WON"),
    ("A", "B", 10_000 - 1_000, "LOST"),
    ("TIE", "B", 10_000, "WON"),  # tie refunds the stake
])
async def test_bet_and_settlement(winner, side, expected_balance, expected_status):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    user_id = await _setup(factory)
    round_id = await _open_round(factory)

    redis = AsyncMock()
    redis.get.return_value = None
    redis.set.return_value = True
    with patch("app.utils.idempotency.get_redis_client", return_value=redis):
        async with factory() as session:
            res = await TeenPattiService(session).place_bet(user_id, TeenPattiBetRequest(round_id=round_id, amount=1_000, side=side), "tp-1")
        assert res.side == side and res.status == "PLACED"

        game_engine = TeenPattiEngine(factory, redis)
        game_engine.state_mgr = AsyncMock()
        async with factory() as session:
            round_obj = await session.get(GameRound, round_id)
        await game_engine.settle(round_obj, {"winner": winner, "payout_x100": 196})

    async with factory() as session:
        wallet = (await session.execute(select(Wallet).where(Wallet.user_id == user_id))).scalar_one()
        entry = (await session.execute(select(GameEntry).where(GameEntry.round_id == round_id))).scalar_one()
    assert wallet.balance == expected_balance
    assert wallet.locked_balance == 0
    assert entry.status == expected_status
    await engine.dispose()


@pytest.mark.asyncio
async def test_bet_rejected_after_betting_closes():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    user_id = await _setup(factory)
    round_id = await _open_round(factory, closes_in=-1)
    async with factory() as session:
        with pytest.raises(BadRequestException, match="closed"):
            await TeenPattiService(session).place_bet(user_id, TeenPattiBetRequest(round_id=round_id, amount=1_000, side="A"), "tp-2")
    await engine.dispose()
