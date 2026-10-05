"""WinGo modes expose the payout table each mode really pays (players' rules and win preview use it)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import create_app
from app.models.game import Game, GameSetting


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add_all([Game(id="wingo_1m", name="WinGo 1m", type="COLOR", is_active=True),
                   Game(id="wingo_3m", name="WinGo 3m", type="COLOR", is_active=True)])
        s.add(GameSetting(game_id="wingo_1m", min_bet=100, max_bet=100000, house_edge_percent=1000,
                          config={"payouts": {"GREEN": 1.89, "RED": 1.89, "COLOR_HALF": 1.42, "SIZE": 1.8}}))
        await s.commit()
    app = create_app()

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    await engine.dispose()


async def test_modes_carry_configured_payouts(client):
    modes = {m["game_id"]: m for m in (await client.get("/api/v1/games/wingo/modes")).json()}
    assert modes["wingo_1m"]["payouts_x100"] == {"GREEN": 189, "RED": 189, "COLOR_HALF": 142, "VIOLET": 450, "NUMBER": 900, "SIZE": 180}
    # A mode without saved payouts falls back to the defaults
    assert modes["wingo_3m"]["payouts_x100"]["GREEN"] == 200
