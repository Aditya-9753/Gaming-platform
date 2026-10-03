"""Lobby "playing now" counts: real players only, per game, recent activity only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.games.simulated_players import BOT_NAMES
from app.main import create_app
from app.models.game import Game, GameEntry, GameRound
from app.models.role import Role
from app.models.user import User
from app.services import live_players


@pytest.fixture
async def client():
    live_players.reset_cache()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    bot = sorted(BOT_NAMES)[0]
    async with factory() as s:
        s.add_all([Role(id=1, name="USER"), Role(id=2, name="ADMIN")])
        s.add_all([
            User(id="p1", username="p1", password_hash="x", role_id=1),
            User(id="p2", username="p2", password_hash="x", role_id=1),
            User(id="p3", username="p3", password_hash="x", role_id=1),
            User(id="bot", username=bot, password_hash="x", role_id=1),
            User(id="staff", username="staff", password_hash="x", role_id=2),
        ])
        for gid in ("aviator", "wingo_1m", "wingo_5m", "mines", "teen_patti"):
            s.add(Game(id=gid, name=gid, type="X", is_active=True))
            s.add(GameRound(id=f"r-{gid}", game_id=gid, round_no=1, status="BETTING", server_seed_hash="h" * 64))
        entries = [
            ("aviator", "p1", now), ("aviator", "p1", now), ("aviator", "p2", now),  # p1 twice -> counted once
            ("aviator", "bot", now), ("aviator", "staff", now),                     # never counted
            ("wingo_1m", "p1", now), ("wingo_5m", "p3", now),                       # both WinGo modes -> color
            ("mines", "p3", now - timedelta(minutes=30)),                           # too old
        ]
        for i, (gid, uid, at) in enumerate(entries):
            s.add(GameEntry(id=f"e{i}", round_id=f"r-{gid}", user_id=uid, bet_amount=100,
                            idempotency_key=f"k{i}", status="PLACED", created_at=at))
        await s.commit()
    app = create_app()

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    await engine.dispose()
    live_players.reset_cache()


async def test_counts_only_recent_real_players_per_game(client):
    r = await client.get("/api/v1/games/live/players")
    assert r.status_code == 200
    assert r.json()["games"] == {"aviator": 2, "color": 2, "mines": 0, "teen_patti": 0}
