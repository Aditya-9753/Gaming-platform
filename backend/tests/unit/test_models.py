"""Unit tests for SQLAlchemy models, constraints, and seeding operations."""

import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.constants import TransactionStatus, TransactionType, UserRole
from app.core.database import Base
from app.models.game import Game, GameEntry, GameRound, GameSetting
from app.models.role import Permission, Role
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from scripts.create_super_admin import create_or_promote_super_admin
from scripts.seed_db import (
    seed_games,
    seed_roles_and_permissions,
    seed_system_settings,
)


@pytest.fixture
async def in_memory_session():
    """Create an isolated in-memory SQLite database session for model testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_seed_database_operations(in_memory_session: AsyncSession):
    """Test seeding roles, permissions, games, and system settings."""
    await seed_roles_and_permissions(in_memory_session)
    await seed_games(in_memory_session)
    await seed_system_settings(in_memory_session)

    # 1. Verify roles seeded
    roles_res = await in_memory_session.execute(select(Role))
    roles = roles_res.scalars().all()
    role_names = {r.name for r in roles}
    for expected_role in UserRole:
        assert expected_role.value in role_names

    # 2. Verify the 4 core games + 4 WinGo modes are seeded
    games_res = await in_memory_session.execute(select(Game))
    games = games_res.scalars().all()
    assert len(games) == 8
    game_ids = {g.id for g in games}
    assert game_ids == {
        "aviator", "mines", "color", "cricket",
        "wingo_30s", "wingo_1m", "wingo_3m", "wingo_5m",
    }

    # 3. Verify game settings configured for each game
    for g in games:
        setting_res = await in_memory_session.execute(
            select(GameSetting).where(GameSetting.game_id == g.id)
        )
        setting = setting_res.scalar_one_or_none()
        assert setting is not None
        assert setting.min_bet >= 100
        assert setting.max_bet > setting.min_bet

    # 4. Verify system settings
    bonus_res = await in_memory_session.execute(
        select(SystemSetting).where(SystemSetting.key == "signup_bonus_paise")
    )
    bonus = bonus_res.scalar_one_or_none()
    assert bonus is not None
    assert bonus.value == "10000"


@pytest.mark.asyncio
async def test_wallet_idempotency_constraint(in_memory_session: AsyncSession):
    """Verify UNIQUE constraint on wallet_transactions idempotency_key."""
    await seed_roles_and_permissions(in_memory_session)

    # Create test user and wallet
    role_res = await in_memory_session.execute(
        select(Role).where(Role.name == UserRole.USER.value)
    )
    user_role = role_res.scalar_one()

    user = User(
        id=str(uuid.uuid4()),
        username="test_gamer",
        email="gamer@test.com",
        password_hash="mockhash",
        role_id=user_role.id,
    )
    in_memory_session.add(user)
    await in_memory_session.flush()

    wallet = Wallet(
        user_id=user.id,
        balance=50000,
        locked_balance=0,
        currency="VIRTUAL",
    )
    in_memory_session.add(wallet)
    await in_memory_session.flush()

    # First transaction
    shared_key = "idemp-key-test-12345"
    tx1 = WalletTransaction(
        wallet_id=wallet.id,
        idempotency_key=shared_key,
        type=TransactionType.BET.value,
        amount=1000,
        balance_before=50000,
        balance_after=49000,
        status=TransactionStatus.COMPLETED.value,
    )
    in_memory_session.add(tx1)
    await in_memory_session.commit()

    # Duplicate transaction with identical idempotency_key must raise IntegrityError
    tx2 = WalletTransaction(
        wallet_id=wallet.id,
        idempotency_key=shared_key,
        type=TransactionType.BET.value,
        amount=1000,
        balance_before=49000,
        balance_after=48000,
        status=TransactionStatus.COMPLETED.value,
    )
    in_memory_session.add(tx2)

    with pytest.raises(IntegrityError):
        await in_memory_session.commit()
    await in_memory_session.rollback()


@pytest.mark.asyncio
async def test_game_entry_idempotency_constraint(in_memory_session: AsyncSession):
    """Verify UNIQUE constraint on game_entries idempotency_key."""
    await seed_roles_and_permissions(in_memory_session)
    await seed_games(in_memory_session)

    role_res = await in_memory_session.execute(
        select(Role).where(Role.name == UserRole.USER.value)
    )
    user_role = role_res.scalar_one()

    user = User(
        id=str(uuid.uuid4()),
        username="player1",
        email="player1@test.com",
        password_hash="mockhash",
        role_id=user_role.id,
    )
    in_memory_session.add(user)
    await in_memory_session.flush()

    round_record = GameRound(
        id=str(uuid.uuid4()),
        game_id="aviator",
        round_no=1,
        status="BETTING",
        server_seed_hash="a" * 64,
    )
    in_memory_session.add(round_record)
    await in_memory_session.flush()

    shared_entry_key = "bet-idemp-key-9999"
    entry1 = GameEntry(
        round_id=round_record.id,
        user_id=user.id,
        idempotency_key=shared_entry_key,
        bet_amount=500,
        payout_amount=0,
        status="PLACED",
    )
    in_memory_session.add(entry1)
    await in_memory_session.commit()

    entry2 = GameEntry(
        round_id=round_record.id,
        user_id=user.id,
        idempotency_key=shared_entry_key,
        bet_amount=500,
        payout_amount=0,
        status="PLACED",
    )
    in_memory_session.add(entry2)

    with pytest.raises(IntegrityError):
        await in_memory_session.commit()
    await in_memory_session.rollback()
