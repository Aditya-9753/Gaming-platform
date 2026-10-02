"""Integration tests for games API endpoints with SQLite in-memory DB."""

from __future__ import annotations

from typing import AsyncGenerator
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import create_app
from scripts.seed_db import seed_games

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def games_client() -> AsyncGenerator[AsyncClient, None]:
    """Test client with isolated SQLite database and seeded games."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        await seed_games(session)

    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_games_endpoint(games_client: AsyncClient):
    """GET /api/v1/games returns the catalog of active games."""
    res = await games_client.get("/api/v1/games")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    game_ids = [g["id"] for g in data]
    assert "aviator" in game_ids
    assert "color" in game_ids
    assert "mines" in game_ids
    assert "cricket" in game_ids


@pytest.mark.asyncio
async def test_get_game_details(games_client: AsyncClient):
    """GET /api/v1/games/{id} returns metadata and limits."""
    res = await games_client.get("/api/v1/games/aviator")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "aviator"
    assert data["min_bet"] > 0
    assert "house_edge_percent" in data


@pytest.mark.asyncio
async def test_get_game_not_found(games_client: AsyncClient):
    """GET /api/v1/games/unknown returns 404."""
    res = await games_client.get("/api/v1/games/nonexistent_game")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_get_game_round_history(games_client: AsyncClient):
    """GET /api/v1/games/{id}/history returns paginated completed rounds."""
    res = await games_client.get("/api/v1/games/aviator/history")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data["items"], list)
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert "total" in data


@pytest.mark.asyncio
async def test_unauthenticated_bet_rejected(games_client: AsyncClient):
    """Placing a wager without authentication returns 401."""
    res = await games_client.post(
        "/api/v1/games/aviator/bet",
        json={"round_id": "fake_round", "amount": 100},
    )
    assert res.status_code == 401
