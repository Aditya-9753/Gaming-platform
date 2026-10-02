"""Pytest configuration and global fixtures.

Provides a self-contained in-memory SQLite test environment so that every
test module that uses `async_client` gets a fresh database without requiring
a live PostgreSQL connection.
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

# Tests exercise production-grade admin security and must never touch the
# hard-coded local accounts; set before app settings are first loaded.
os.environ.setdefault("ADMIN_2FA_REQUIRED", "true")
os.environ.setdefault("SEED_DEFAULT_ACCOUNTS", "false")
os.environ.setdefault("RUN_GAME_ENGINES", "false")
# Isolate tests from the dev Redis (db 0): idempotency keys / round state
# leaking across runs caused spurious 409s and could corrupt live games.
_TEST_REDIS_URL = "redis://localhost:6380/15"
os.environ.setdefault("REDIS_URL", _TEST_REDIS_URL)

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import create_app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
def _clean_test_redis() -> None:
    """Start every run with an empty test Redis database (only the test DB)."""
    if os.environ.get("REDIS_URL") != _TEST_REDIS_URL:
        return
    try:
        import redis as sync_redis

        sync_redis.Redis.from_url(_TEST_REDIS_URL, socket_connect_timeout=1).flushdb()
    except Exception:
        pass  # Redis not running: tests that need it fall back / skip as before


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with an in-memory SQLite database.

    Every test that uses this fixture gets:
    - A fresh SQLite database with all tables created
    - The `get_db` dependency overridden to use the in-memory DB
    - No network calls to a real PostgreSQL instance
    """
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await engine.dispose()
