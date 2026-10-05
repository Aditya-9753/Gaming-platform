from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.constants import GameRoundLifecycle, RoundStatus
from app.core.exceptions import BadRequestException, ConflictException
from app.core.database import Base
from app.games.aviator.rules import crash_elapsed_seconds
from app.games.aviator.service import AviatorService
from app.games.base.settlement import RoundSettlementManager
from app.games.base.state import can_transition
from app.games.color.rules import (
    ColourResult,
    compute_colour,
    configured_payout_x100,
    round_timing_seconds,
)
from app.games.color.service import ColorService
from app.main import create_app
from app.models.game import Game, GameEntry, GameRound
from app.models.role import Role
from app.models.user import User
from app.models.wallet import Wallet
from app.services.wallet_service import WalletService


def test_game_specific_lifecycle_transitions():
    assert can_transition(GameRoundLifecycle.WAITING.value, GameRoundLifecycle.BETTING_OPEN.value)
    assert can_transition("BETTING_OPEN", "RUNNING")
    assert can_transition("RUNNING", GameRoundLifecycle.CRASHED.value)
    assert can_transition(GameRoundLifecycle.CRASHED.value, GameRoundLifecycle.SETTLING.value)
    assert can_transition(GameRoundLifecycle.SETTLING.value, GameRoundLifecycle.HISTORY.value)
    assert can_transition(GameRoundLifecycle.CREATED.value, GameRoundLifecycle.OPEN.value)
    assert can_transition(GameRoundLifecycle.OPEN.value, GameRoundLifecycle.LOCKED.value)
    assert can_transition(GameRoundLifecycle.LOCKED.value, GameRoundLifecycle.RESULT.value)
    assert can_transition(GameRoundLifecycle.RESULT.value, GameRoundLifecycle.SETTLED.value)
    assert can_transition(GameRoundLifecycle.SETTLED.value, GameRoundLifecycle.HISTORY.value)


def test_color_timing_and_payouts_follow_game_settings():
    assert round_timing_seconds(
        {"timer_length_seconds": 20, "lock_before_end_seconds": 3}
    ) == (20.0, 3.0)
    payout_settings = {"RED": 3.25, "GREEN": 3.25, "VIOLET": 3.25}
    assert configured_payout_x100(ColourResult.GREEN, payout_settings) == 325
    assert (
        compute_colour("server", "client", 1, payout_multipliers=payout_settings)
        .payout_x100
        == 325
    )


def _aviator_service(monkeypatch, now, started_at):
    session = AsyncMock()
    service = AviatorService(session, clock=lambda: now)
    settings = SimpleNamespace(config={}, house_edge_percent=300)
    monkeypatch.setattr(
        service,
        "_enabled_game_settings",
        AsyncMock(return_value=settings),
    )
    round_obj = SimpleNamespace(
        id="round-1",
        game_id="aviator",
        round_no=1,
        status=RoundStatus.RUNNING.value,
        started_at=started_at,
        server_seed="seed",
        client_seed="client",
        result={},
    )
    entry = SimpleNamespace(
        id="entry-1",
        user_id="user-1",
        round_id="round-1",
        bet_amount=100,
        status="PLACED",
        payout_amount=0,
        multiplier=None,
        selection={},
    )
    service.round_repo.get_by_id = AsyncMock(return_value=round_obj)
    service.entry_repo.get_by_id_for_update = AsyncMock(return_value=entry)

    async def update_entry(entry_id, status, payout_amount, multiplier=None):
        entry.status = status
        entry.payout_amount = payout_amount
        entry.multiplier = multiplier
        return entry

    service.entry_repo.update_settlement = AsyncMock(side_effect=update_entry)
    service.wallet_svc.settle_win = AsyncMock()
    return service, entry


@pytest.mark.asyncio
async def test_aviator_cashout_is_rejected_at_crash_time(monkeypatch):
    now = datetime.now(timezone.utc)
    crash_time = crash_elapsed_seconds(200)
    service, _ = _aviator_service(
        monkeypatch,
        now,
        now - timedelta(seconds=crash_time),
    )
    monkeypatch.setattr(
        "app.games.aviator.service.compute_crash_point",
        lambda *args, **kwargs: 200,
    )

    with pytest.raises(BadRequestException, match="crashed"):
        await service.cashout(
            "user-1", "round-1", "entry-1", idempotency_key="cashout-1"
        )
    service.wallet_svc.settle_win.assert_not_awaited()


@pytest.mark.asyncio
async def test_aviator_cashout_before_crash_and_double_cashout(monkeypatch):
    now = datetime.now(timezone.utc)
    crash_time = crash_elapsed_seconds(200)
    service, entry = _aviator_service(
        monkeypatch,
        now,
        now - timedelta(seconds=crash_time - 0.01),
    )
    monkeypatch.setattr(
        "app.games.aviator.service.compute_crash_point",
        lambda *args, **kwargs: 200,
    )

    result = await service.cashout(
        "user-1", "round-1", "entry-1", idempotency_key="cashout-1"
    )
    assert 1.0 <= result.multiplier < 2.0
    assert result.payout_amount == entry.payout_amount
    assert service.wallet_svc.settle_win.await_args.kwargs["win_amount_paise"] == (
        result.payout_amount - entry.bet_amount
    )

    replay = await service.cashout(
        "user-1", "round-1", "entry-1", idempotency_key="cashout-1"
    )
    assert replay.payout_amount == result.payout_amount
    with pytest.raises(ConflictException):
        await service.cashout(
            "user-1", "round-1", "entry-1", idempotency_key="cashout-2"
        )
    service.wallet_svc.settle_win.assert_awaited_once()


@pytest.mark.asyncio
async def test_aviator_auto_cashout_uses_stored_target(monkeypatch):
    now = datetime.now(timezone.utc)
    crash_time = crash_elapsed_seconds(200)
    service, entry = _aviator_service(
        monkeypatch,
        now,
        now - timedelta(seconds=crash_time - 2),
    )
    entry.selection = {"auto_cashout": 1.5}
    monkeypatch.setattr(
        "app.games.aviator.service.compute_crash_point",
        lambda *args, **kwargs: 200,
    )

    result = await service.cashout(
        "user-1",
        "round-1",
        "entry-1",
        idempotency_key="auto-cashout-1",
        automatic=True,
    )
    assert result.multiplier == 1.5


@pytest.mark.asyncio
async def test_aviator_bet_at_or_after_server_close_is_rejected(monkeypatch):
    now = datetime.now(timezone.utc)
    service = AviatorService(AsyncMock(), clock=lambda: now)
    service.entry_repo.get_by_idempotency_key = AsyncMock(return_value=None)
    service.entry_repo.create_entry = AsyncMock()
    service.round_repo.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            id="round-1",
            game_id="aviator",
            status=GameRoundLifecycle.BETTING_OPEN.value,
            result={"betting_closes_at": now.isoformat()},
        )
    )
    service.wallet_svc.place_bet = AsyncMock()
    monkeypatch.setattr(
        service,
        "_enabled_game_settings",
        AsyncMock(
            return_value=SimpleNamespace(
                min_bet=100,
                max_bet=5_000,
                config={},
            )
        ),
    )

    with pytest.raises(BadRequestException, match="closed"):
        await service.place_bet(
            "user-1", "round-1", 100, idempotency_key="bet-after-close"
        )
    service.wallet_svc.place_bet.assert_not_awaited()
    service.entry_repo.create_entry.assert_not_awaited()


def _color_service(now, status, close_at):
    service = ColorService(AsyncMock(), clock=lambda: now)
    game = SimpleNamespace(
        is_active=True,
        settings=SimpleNamespace(min_bet=100, max_bet=5000),
    )
    round_obj = SimpleNamespace(
        id="color-round",
        game_id="color",
        status=status,
        result={"betting_closes_at": close_at.isoformat()},
    )
    service.game_repo.get_by_id = AsyncMock(return_value=game)
    service.entry_repo.get_by_idempotency_key = AsyncMock(return_value=None)
    service.round_repo.get_by_id = AsyncMock(return_value=round_obj)
    service.entry_repo.create_entry = AsyncMock(
        side_effect=lambda **kwargs: SimpleNamespace(
            id=f"entry-{kwargs['user_id']}",
            round_id=kwargs["round_id"],
            bet_amount=kwargs["bet_amount"],
            status="PLACED",
        )
    )
    service.wallet_svc.place_bet = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_color_bet_after_lock_is_rejected():
    now = datetime.now(timezone.utc)
    service = _color_service(now, GameRoundLifecycle.OPEN.value, now)

    with pytest.raises(BadRequestException, match="closed"):
        await service.place_bet(
            "user-1", "color-round", 100, ColourResult.RED, "color-key"
        )
    service.wallet_svc.place_bet.assert_not_awaited()


@pytest.mark.asyncio
async def test_simultaneous_color_bets_are_both_accepted():
    now = datetime.now(timezone.utc)
    service = _color_service(
        now, GameRoundLifecycle.OPEN.value, now + timedelta(seconds=10)
    )

    bets = await asyncio.gather(
        service.place_bet("user-1", "color-round", 100, ColourResult.RED, "red-key"),
        service.place_bet("user-2", "color-round", 200, ColourResult.GREEN, "green-key"),
    )
    assert [bet.bet_amount for bet in bets] == [100, 200]
    assert service.wallet_svc.place_bet.await_count == 2


TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest.mark.asyncio
async def test_color_settlement_is_correct_and_idempotent():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    user_id = str(uuid.uuid4())
    round_id = str(uuid.uuid4())

    async with session_factory() as session:
        role = Role(name=f"TEST_{uuid.uuid4().hex[:8]}", description="test role")
        session.add(role)
        await session.flush()
        session.add(Game(id="color", name="Color", type="COLOR", is_active=True))
        user = User(
            id=user_id,
            username=f"user_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.test",
            password_hash="test",
            role_id=role.id,
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.flush()
        session.add(
            Wallet(
                id=str(uuid.uuid4()),
                user_id=user_id,
                balance=10_000,
                locked_balance=0,
                currency="VIRTUAL",
                is_frozen=False,
            )
        )
        round_obj = GameRound(
            id=round_id,
            game_id="color",
            round_no=1,
            status=GameRoundLifecycle.RESULT.value,
            server_seed_hash="a" * 64,
            server_seed="seed",
            client_seed="client",
        )
        session.add(round_obj)
        await session.commit()
        await WalletService(session).place_bet(
            user_id=user_id,
            amount_paise=1_000,
            idempotency_key="color-bet",
            reference="color:round:bet",
        )
        session.add(
            GameEntry(
                id=str(uuid.uuid4()),
                round_id=round_id,
                user_id=user_id,
                idempotency_key="color-entry",
                bet_amount=1_000,
                selection={"colour": "RED"},
                status="PLACED",
            )
        )
        await session.commit()

    redis = AsyncMock()
    redis.get.return_value = None
    redis.set.return_value = True
    with patch("app.utils.idempotency.get_redis_client", return_value=redis):
        settlement = RoundSettlementManager(session_factory)

        def evaluate(entry):
            if (entry.selection or {}).get("colour") == "RED":
                return True, 200, entry.bet_amount * 2
            return False, 0, 0

        await settlement.settle_round(
            round_id,
            evaluate,
            {"winning_colour": "RED", "payout_x100": 200},
        )
        await settlement.settle_round(
            round_id,
            evaluate,
            {"winning_colour": "RED", "payout_x100": 200},
        )

    async with session_factory() as session:
        wallet = (
            await session.execute(select(Wallet).where(Wallet.user_id == user_id))
        ).scalar_one()
        entry = (
            await session.execute(select(GameEntry).where(GameEntry.round_id == round_id))
        ).scalar_one()
        assert wallet.balance == 11_000
        assert wallet.locked_balance == 0
        assert entry.status == "WON"
        assert entry.payout_amount == 2_000

    await engine.dispose()


def test_new_game_action_routes_require_idempotency_headers():
    paths = create_app().openapi()["paths"]
    for path in ("/api/v1/games/aviator/action", "/api/v1/games/color/action"):
        operation = paths[path]["post"]
        header = next(
            parameter
            for parameter in operation["parameters"]
            if parameter["name"] == "Idempotency-Key"
        )
        assert header["in"] == "header"
        assert header["required"] is True
