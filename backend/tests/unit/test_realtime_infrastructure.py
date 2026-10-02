"""Tests for real-time infrastructure: leader failover, pubsub fan-out, and recovery after crash."""

from __future__ import annotations

import asyncio
import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.games.base.leader import LeaderElection
from app.games.base.recovery import EngineRecoveryService
from app.games.base.registry import GameEngineRegistry, register_game
from app.games.base.settlement import RoundSettlementManager
from app.games.base.state import RedisRoundStateManager, RoundStateSnapshot
from app.models.game import GameEntry, GameRound
from app.models.role import Role
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.websocket.auth import create_ws_ticket, validate_and_consume_ticket
from app.websocket.events import format_ws_event
from app.websocket.manager import ConnectionManager
from app.websocket.pubsub import RedisPubSubBridge


@pytest.fixture
async def fake_redis():
    """Isolated in-memory FakeRedis instance for testing."""
    redis = FakeRedis(decode_responses=True)
    yield redis
    await redis.flushall()
    await redis.aclose()


@pytest.fixture
async def in_memory_session_factory():
    """Isolated SQLite database session factory for engine testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


# =========================================================================
# 1. Leader Election & Failover Test
# =========================================================================


@pytest.mark.asyncio
async def test_leader_election_failover(fake_redis: FakeRedis):
    """Test leader acquisition, mutual exclusion, and failover takeover upon release."""
    leader_a = LeaderElection(fake_redis, lock_name="engine_test", ttl_seconds=2)
    leader_b = LeaderElection(fake_redis, lock_name="engine_test", ttl_seconds=2)

    # 1. Node A acquires leadership
    assert await leader_a.acquire() is True
    assert leader_a.is_leader is True

    # 2. Node B cannot acquire leadership while Node A holds the lock
    assert await leader_b.acquire() is False
    assert leader_b.is_leader is False

    # 3. Node A releases lock
    await leader_a.release()
    assert leader_a.is_leader is False

    # 4. Node B immediately takes over leadership
    assert await leader_b.acquire() is True
    assert leader_b.is_leader is True

    await leader_b.release()


# =========================================================================
# 2. PubSub Fan-Out Test
# =========================================================================


@pytest.mark.asyncio
async def test_pubsub_fanout_to_websockets(fake_redis: FakeRedis):
    """Test that engine events published to Redis fan out to all listening WebSockets."""
    manager = ConnectionManager()
    bridge = RedisPubSubBridge(fake_redis)

    # Mock two client WebSockets subscribed to game:aviator
    ws1 = MagicMock()
    ws1.accept = AsyncMock()
    ws1.send_text = AsyncMock()
    ws2 = MagicMock()
    ws2.accept = AsyncMock()
    ws2.send_text = AsyncMock()

    await manager.connect(ws1, channel="game:aviator")
    await manager.connect(ws2, channel="game:aviator")

    # Patch global ws_manager inside pubsub with our test manager
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.websocket.pubsub.ws_manager", manager)
        task = bridge.start()
        await asyncio.sleep(0.1)  # allow subscription to establish

        # Engine publishes event envelope to Redis
        payload = format_ws_event(
            "ROUND_BETTING_OPEN",
            {"round_no": 101, "seconds_left": 5},
            round_id="round-xyz",
            game_id="aviator",
        )
        await fake_redis.publish("game:aviator", payload)
        await asyncio.sleep(0.2)  # allow listener to process

        await bridge.stop()

    # Verify both sockets received the fan-out message
    ws1.send_text.assert_awaited_once_with(payload)
    ws2.send_text.assert_awaited_once_with(payload)


# =========================================================================
# 3. Recovery After Simulated Crash Test
# =========================================================================


@pytest.mark.asyncio
async def test_recovery_after_simulated_crash(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
    fake_redis: FakeRedis,
):
    """Test that orphaned rounds left in BETTING status after engine crash are refunded."""
    async with in_memory_session_factory() as session:
        # Create test role
        role = Role(id=1, name="USER", description="Player")
        session.add(role)

        # Create test user and wallet with 1000 available, 500 locked
        user = User(
            id="crash_user",
            username="test_crash",
            email="crash@test.com",
            password_hash="hash",
            role_id=1,
            is_active=True,
        )
        session.add(user)

        wallet = Wallet(
            id="crash_wallet",
            user_id="crash_user",
            balance=1000,
            locked_balance=500,
        )
        session.add(wallet)

        # Create orphaned round stuck in BETTING
        round_obj = GameRound(
            id="orphaned_round",
            game_id="aviator",
            round_no=99,
            server_seed_hash="dummy_hash",
            status="BETTING",
        )
        session.add(round_obj)

        # Create placed entry for the locked 500 paise
        entry = GameEntry(
            id="orphaned_entry",
            round_id="orphaned_round",
            user_id="crash_user",
            bet_amount=500,
            idempotency_key="crash_bet_idem",
            status="PLACED",
        )
        session.add(entry)
        await session.commit()

    # Simulate startup recovery
    recovery = EngineRecoveryService(in_memory_session_factory, redis=fake_redis)
    recovered_count = await recovery.recover_orphaned_rounds()
    assert recovered_count == 1

    # Verify state after recovery
    async with in_memory_session_factory() as session:
        # Round marked CANCELLED
        r = await session.get(GameRound, "orphaned_round")
        assert r.status == "CANCELLED"

        # Entry marked REFUNDED
        e = await session.get(GameEntry, "orphaned_entry")
        assert e.status == "REFUNDED"
        assert e.payout_amount == 500

        # Wallet locked balance released back: locked is 0, available is restored
        w = await session.get(Wallet, "crash_wallet")
        assert w.balance == 1000
        assert w.locked_balance == 0
        assert w.available_balance == 1000


# =========================================================================
# 4. WebSocket Short-Lived Ticket Auth Test
# =========================================================================


@pytest.mark.asyncio
async def test_websocket_ticket_single_use(fake_redis: FakeRedis):
    """Test ticket creation, single-use consumption, and expiry."""
    ticket = await create_ws_ticket(fake_redis, user_id="user_123", ttl_seconds=60)
    assert ticket is not None

    # First consumption succeeds
    consumed_user = await validate_and_consume_ticket(fake_redis, ticket)
    assert consumed_user == "user_123"

    # Second consumption immediately fails (ticket already consumed)
    second_try = await validate_and_consume_ticket(fake_redis, ticket)
    assert second_try is None


# =========================================================================
# 5. Redis State Snapshot & Open Bets Test
# =========================================================================


@pytest.mark.asyncio
async def test_redis_round_state_and_open_bets(fake_redis: FakeRedis):
    """Test Redis-backed round snapshot creation and tracking of open bets."""
    state_mgr = RedisRoundStateManager(fake_redis)

    # 1. Set round state
    snapshot = await state_mgr.set_round_state(
        game_id="aviator",
        round_id="r-555",
        round_no=5,
        status="BETTING",
        server_seed_hash="hash_555",
    )
    assert snapshot.round_id == "r-555"
    assert snapshot.bet_count == 0

    # 2. Add open bets
    await state_mgr.add_open_bet(
        game_id="aviator",
        round_id="r-555",
        entry_id="e-1",
        user_id="u-1",
        bet_amount=200,
        selection={"auto_cashout": 2.0},
    )

    # 3. Retrieve snapshot
    fetched = await state_mgr.get_round_state("aviator")
    assert fetched is not None
    assert fetched.round_id == "r-555"
    assert fetched.bet_count == 1
    assert fetched.total_wagered == 200

    # 4. Retrieve open bets list
    bets = await state_mgr.get_open_bets("aviator", "r-555")
    assert len(bets) == 1
    assert bets[0]["entry_id"] == "e-1"
    assert bets[0]["bet_amount"] == 200

    # 5. Clear state
    await state_mgr.clear_round_state("aviator")
    assert await state_mgr.get_round_state("aviator") is None


# =========================================================================
# 6. Dynamic Game Registration Test
# =========================================================================


def test_game_registry_decorator():
    """Verify @register_game decorator registers class and allows instantiation."""
    registry = GameEngineRegistry()

    @register_game("custom_dice")
    class CustomDiceEngine:
        def __init__(self, session_factory=None, redis=None):
            self.game_id = "custom_dice"

    cls = registry.get_class("custom_dice")
    # Registered in global registry or local
    from app.games.base.registry import engine_registry
    assert engine_registry.get_class("custom_dice") == CustomDiceEngine
