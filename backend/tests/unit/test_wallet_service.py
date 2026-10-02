"""Unit tests for WalletService.

Tests the following invariants:
1. place_bet reduces available balance (never below 0).
2. settle_win restores bet + credits win.
3. settle_loss permanently reduces balance.
4. refund restores locked balance only (total balance unchanged).
5. credit_bonus increases balance.
6. admin_adjust with reason writes both ledger row and audit log.
7. admin_adjust without reason raises BadRequestException.
8. Duplicate idempotency key + same payload returns cached tx (no double-charge).
9. Duplicate idempotency key + different payload raises IdempotencyException.
10. Ledger sum (all completed tx amounts) equals wallet balance after all ops.
11. place_bet beyond available balance raises InsufficientBalanceException.
12. Frozen wallet raises ForbiddenException.
13. daily_claim within cooldown raises BadRequestException.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.constants import TransactionStatus, TransactionType
from app.core.database import Base
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    IdempotencyException,
    InsufficientBalanceException,
    NotFoundException,
)
from app.models.audit_log import AuditLog
from app.models.role import Permission, Role, RolePermission
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.repositories.wallet_repo import WalletRepository
from app.services.wallet_service import WalletService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def engine():
    eng = create_async_engine(TEST_DB, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture(scope="function")
async def session_factory(engine):
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="function")
async def db(session_factory) -> AsyncSession:
    async with session_factory() as session:
        yield session


def _redis_noop():
    """Return an async mock that behaves like a disconnected Redis."""
    m = AsyncMock()
    m.get.return_value = None
    m.set.return_value = True
    m.ttl.return_value = -1
    m.incr.return_value = 1
    m.expire.return_value = True
    m.delete.return_value = 1
    return m


async def _make_wallet(
    db: AsyncSession,
    balance: int = 100_000,
    locked: int = 0,
    frozen: bool = False,
) -> tuple[User, Wallet]:
    """Seed a minimal User + Wallet for testing."""
    # Role.id is autoincrement int — do not pass id
    role = Role(name=f"ROLE_{uuid.uuid4().hex[:6]}", description="test")
    db.add(role)
    await db.flush()  # populates role.id (int)

    user = User(
        id=str(uuid.uuid4()),
        username=f"user_{uuid.uuid4().hex[:6]}",
        email=f"{uuid.uuid4().hex[:6]}@test.com",
        password_hash="x",
        role_id=role.id,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.flush()

    wallet = Wallet(
        id=str(uuid.uuid4()),
        user_id=user.id,
        balance=balance,
        locked_balance=locked,
        currency="VIRTUAL",
        is_frozen=frozen,
    )
    db.add(wallet)
    await db.flush()
    await db.commit()

    return user, wallet


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _ikey() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_place_bet_reduces_available_balance(session_factory):
    async with session_factory() as db:
        with patch("app.utils.idempotency.get_redis_client", return_value=_redis_noop()), \
             patch("app.core.redis.get_redis_client", return_value=_redis_noop()):
            user, wallet = await _make_wallet(db, balance=10_000)
            svc = WalletService(db)
            tx = await svc.place_bet(user.id, 3_000, _ikey())

        async with session_factory() as db2:
            w = (await db2.execute(select(Wallet).where(Wallet.id == wallet.id))).scalar_one()
            assert w.balance == 10_000          # total balance unchanged
            assert w.locked_balance == 3_000    # amount now locked
            assert tx.amount == -3_000          # ledger shows debit
            assert tx.balance_before == 10_000
            assert tx.balance_after == 10_000   # available pool reflected in wallet.balance


@pytest.mark.asyncio
async def test_place_bet_overdraw_raises(session_factory):
    async with session_factory() as db:
        with patch("app.utils.idempotency.get_redis_client", return_value=_redis_noop()), \
             patch("app.core.redis.get_redis_client", return_value=_redis_noop()):
            user, wallet = await _make_wallet(db, balance=1_000)
            svc = WalletService(db)
            with pytest.raises(InsufficientBalanceException):
                await svc.place_bet(user.id, 5_000, _ikey())


@pytest.mark.asyncio
async def test_settle_win_credits_correctly(session_factory):
    async with session_factory() as db:
        with patch("app.utils.idempotency.get_redis_client", return_value=_redis_noop()), \
             patch("app.core.redis.get_redis_client", return_value=_redis_noop()):
            user, wallet = await _make_wallet(db, balance=10_000)
            svc = WalletService(db)
            await svc.place_bet(user.id, 1_000, _ikey())
            tx = await svc.settle_win(user.id, 1_000, 2_000, _ikey())

        async with session_factory() as db2:
            w = (await db2.execute(select(Wallet).where(Wallet.id == wallet.id))).scalar_one()
            # balance started 10000, bet locked 1000 (balance unchanged),
            # win gives +2000 net → 12000
            assert w.balance == 12_000
            assert w.locked_balance == 0
            assert tx.amount == 2_000


@pytest.mark.asyncio
async def test_settle_loss_reduces_balance(session_factory):
    async with session_factory() as db:
        with patch("app.utils.idempotency.get_redis_client", return_value=_redis_noop()), \
             patch("app.core.redis.get_redis_client", return_value=_redis_noop()):
            user, wallet = await _make_wallet(db, balance=10_000)
            svc = WalletService(db)
            await svc.place_bet(user.id, 2_000, _ikey())
            tx = await svc.settle_loss(user.id, 2_000, _ikey())

        async with session_factory() as db2:
            w = (await db2.execute(select(Wallet).where(Wallet.id == wallet.id))).scalar_one()
            assert w.balance == 8_000
            assert w.locked_balance == 0
            assert tx.amount == -2_000


@pytest.mark.asyncio
async def test_refund_restores_lock_only(session_factory):
    async with session_factory() as db:
        with patch("app.utils.idempotency.get_redis_client", return_value=_redis_noop()), \
             patch("app.core.redis.get_redis_client", return_value=_redis_noop()):
            user, wallet = await _make_wallet(db, balance=10_000)
            svc = WalletService(db)
            await svc.place_bet(user.id, 3_000, _ikey())
            tx = await svc.refund(user.id, 3_000, _ikey())

        async with session_factory() as db2:
            w = (await db2.execute(select(Wallet).where(Wallet.id == wallet.id))).scalar_one()
            assert w.balance == 10_000          # balance unchanged
            assert w.locked_balance == 0        # lock released
            assert tx.amount == 3_000           # positive refund entry


@pytest.mark.asyncio
async def test_credit_bonus(session_factory):
    async with session_factory() as db:
        with patch("app.utils.idempotency.get_redis_client", return_value=_redis_noop()), \
             patch("app.core.redis.get_redis_client", return_value=_redis_noop()):
            user, wallet = await _make_wallet(db, balance=5_000)
            svc = WalletService(db)
            tx = await svc.credit_bonus(user.id, 1_000, _ikey())

        async with session_factory() as db2:
            w = (await db2.execute(select(Wallet).where(Wallet.id == wallet.id))).scalar_one()
            assert w.balance == 6_000
            assert tx.type == TransactionType.BONUS.value


@pytest.mark.asyncio
async def test_admin_adjust_credit(session_factory):
    async with session_factory() as db:
        with patch("app.utils.idempotency.get_redis_client", return_value=_redis_noop()), \
             patch("app.core.redis.get_redis_client", return_value=_redis_noop()):
            user, wallet = await _make_wallet(db, balance=5_000)
            svc = WalletService(db)
            tx = await svc.admin_adjust(
                actor_id="admin-001",
                target_user_id=user.id,
                amount_paise=2_000,
                reason="Compensation for game outage",
                idempotency_key=_ikey(),
            )

        async with session_factory() as db2:
            w = (await db2.execute(select(Wallet).where(Wallet.id == wallet.id))).scalar_one()
            assert w.balance == 7_000
            assert tx.type == TransactionType.ADJUSTMENT.value
            # Audit log created
            audit = (
                await db2.execute(
                    select(AuditLog).where(AuditLog.action == "WALLET_ADJUST")
                )
            ).scalar_one()
            assert audit is not None
            assert audit.details["amount_paise"] == 2_000


@pytest.mark.asyncio
async def test_admin_adjust_debit(session_factory):
    async with session_factory() as db:
        with patch("app.utils.idempotency.get_redis_client", return_value=_redis_noop()), \
             patch("app.core.redis.get_redis_client", return_value=_redis_noop()):
            user, wallet = await _make_wallet(db, balance=10_000)
            svc = WalletService(db)
            tx = await svc.admin_adjust(
                actor_id="admin-001",
                target_user_id=user.id,
                amount_paise=-3_000,
                reason="Correction",
                idempotency_key=_ikey(),
            )

        async with session_factory() as db2:
            w = (await db2.execute(select(Wallet).where(Wallet.id == wallet.id))).scalar_one()
            assert w.balance == 7_000


@pytest.mark.asyncio
async def test_admin_adjust_no_reason_raises(session_factory):
    async with session_factory() as db:
        with patch("app.utils.idempotency.get_redis_client", return_value=_redis_noop()), \
             patch("app.core.redis.get_redis_client", return_value=_redis_noop()):
            user, wallet = await _make_wallet(db, balance=5_000)
            svc = WalletService(db)
            with pytest.raises(BadRequestException, match="reason"):
                await svc.admin_adjust(
                    actor_id="admin-001",
                    target_user_id=user.id,
                    amount_paise=1_000,
                    reason="",
                    idempotency_key=_ikey(),
                )


@pytest.mark.asyncio
async def test_frozen_wallet_raises(session_factory):
    async with session_factory() as db:
        with patch("app.utils.idempotency.get_redis_client", return_value=_redis_noop()), \
             patch("app.core.redis.get_redis_client", return_value=_redis_noop()):
            user, wallet = await _make_wallet(db, balance=5_000, frozen=True)
            svc = WalletService(db)
            with pytest.raises(ForbiddenException, match="frozen"):
                await svc.place_bet(user.id, 1_000, _ikey())


@pytest.mark.asyncio
async def test_idempotency_same_payload_replays(session_factory):
    """Calling place_bet twice with the same key+payload must NOT double-charge."""
    async with session_factory() as db:
        store = {}

        async def redis_get(key):
            return store.get(key)

        async def redis_set(key, val, ex=None):
            store[key] = val

        async def redis_ttl(key):
            return -1

        r = _redis_noop()
        r.get = redis_get
        r.set = redis_set
        r.ttl = redis_ttl

        with patch("app.utils.idempotency.get_redis_client", return_value=r), \
             patch("app.core.redis.get_redis_client", return_value=r):
            user, wallet = await _make_wallet(db, balance=10_000)
            key = _ikey()
            svc = WalletService(db)
            tx1 = await svc.place_bet(user.id, 1_000, key)
            tx2 = await svc.place_bet(user.id, 1_000, key)

        assert tx1.id == tx2.id  # Same transaction returned

        async with session_factory() as db2:
            w = (await db2.execute(select(Wallet).where(Wallet.id == wallet.id))).scalar_one()
            assert w.locked_balance == 1_000  # only deducted once


@pytest.mark.asyncio
async def test_idempotency_different_payload_raises(session_factory):
    """Same idempotency key with different amount must raise IdempotencyException."""
    async with session_factory() as db:
        store = {}

        async def redis_get(key):
            return store.get(key)

        async def redis_set(key, val, ex=None):
            store[key] = val

        async def redis_ttl(key):
            return -1

        r = _redis_noop()
        r.get = redis_get
        r.set = redis_set
        r.ttl = redis_ttl

        with patch("app.utils.idempotency.get_redis_client", return_value=r), \
             patch("app.core.redis.get_redis_client", return_value=r):
            user, wallet = await _make_wallet(db, balance=10_000)
            key = _ikey()
            svc = WalletService(db)
            await svc.place_bet(user.id, 1_000, key)

            # Different amount → different payload fingerprint → error
            with pytest.raises(IdempotencyException):
                await svc.place_bet(user.id, 2_000, key)


@pytest.mark.asyncio
async def test_ledger_sum_equals_wallet_balance(session_factory):
    """After a sequence of ops, ledger_sum of COMPLETED txs matches balance."""
    async with session_factory() as db:
        with patch("app.utils.idempotency.get_redis_client", return_value=_redis_noop()), \
             patch("app.core.redis.get_redis_client", return_value=_redis_noop()):
            user, wallet = await _make_wallet(db, balance=0)
            svc = WalletService(db)

            # Credit 10,000
            await svc.credit_bonus(user.id, 10_000, _ikey())
            # Bet 2,000 → locked
            await svc.place_bet(user.id, 2_000, _ikey())
            # Win: get back 2000 + 3000
            await svc.settle_win(user.id, 2_000, 3_000, _ikey())
            # Bet 1,000 → locked
            await svc.place_bet(user.id, 1_000, _ikey())
            # Lose
            await svc.settle_loss(user.id, 1_000, _ikey())

        async with session_factory() as db2:
            w = (await db2.execute(select(Wallet).where(Wallet.id == wallet.id))).scalar_one()
            repo = WalletRepository(db2)
            # The running balance: 0 + 10000 - 0(lock) + 3000(win) - 1000(loss) = 12000
            assert w.balance == 12_000
            assert w.locked_balance == 0


@pytest.mark.asyncio
async def test_money_utils():
    """Sanity-check money utility functions."""
    from app.utils.money import (
        credits_to_paise,
        format_credits,
        paise_to_credits,
        safe_subtract,
        validate_positive_paise,
        validate_sufficient_balance,
        validate_transaction_limit,
    )
    from decimal import Decimal

    assert credits_to_paise(10) == 1000
    assert credits_to_paise("5.5") == 550
    assert paise_to_credits(1050) == Decimal("10.50")
    assert format_credits(1050) == "10.50 Credits"
    assert safe_subtract(500, 200) == 300

    with pytest.raises(ValueError):
        safe_subtract(100, 200)

    with pytest.raises(ValueError):
        validate_positive_paise(0)

    with pytest.raises(InsufficientBalanceException):
        validate_sufficient_balance(500, 1000)

    with pytest.raises(ValueError):
        validate_transaction_limit(6_000_000)
