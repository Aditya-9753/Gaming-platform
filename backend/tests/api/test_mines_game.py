"""Server-authoritative Mines session behavior."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import create_app
from app.models.game import Game, GameEntry, GameSetting
from app.models.role import Role
from app.models.user import User
from app.models.wallet import Wallet
from app.services.fairness_service import FairnessService
from app.games.mines.rules import compute_mines_multiplier_bp


@pytest.fixture
async def mines_env(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.api.v1.games.routes.get_redis_client", lambda: None)
    async with factory() as session:
        role = Role(id=1, name="USER")
        user = User(
            id="mines-player",
            username="mines-player",
            email="mines@example.test",
            password_hash="unused",
            role_id=1,
            is_active=True,
        )
        session.add_all([role, user])
        session.add(Wallet(user_id=user.id, balance=100_000, locked_balance=0))
        session.add(
            Game(id="mines", name="Mines", type="MINES", is_active=True)
        )
        session.add(GameSetting(game_id="mines", min_bet=100, max_bet=50_000))
        await session.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    token = create_access_token({"sub": "mines-player", "role": "USER"})
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield {"client": client, "headers": {"Authorization": f"Bearer {token}"}, "factory": factory}
    await engine.dispose()


@pytest.mark.asyncio
async def test_mines_cannot_reveal_twice_and_seed_verifies_after_bust(mines_env):
    client = mines_env["client"]
    headers = mines_env["headers"]
    start = await client.post(
        "/api/v1/games/mines/action",
        headers={**headers, "Idempotency-Key": "mines-start-1"},
        json={
            "action": "start",
            "bet_amount": 1_000,
            "mine_count": 3,
            "client_seed": "client-seed-xyz",
        },
    )
    assert start.status_code == 200
    round_id = start.json()["round_id"]
    assert start.json()["mines"] is None
    assert start.json()["server_seed"] is None
    async with mines_env["factory"]() as session:
        entry = await session.get(GameEntry, start.json()["entry_id"])
        mine_tile = entry.selection["mines"][0]
        safe_tile = next(tile for tile in range(25) if tile not in entry.selection["mines"])

    safe = await client.post(
        "/api/v1/games/mines/action",
        headers={**headers, "Idempotency-Key": "mines-reveal-safe"},
        json={"action": "reveal", "tile_index": safe_tile},
    )
    assert safe.status_code == 200
    repeated = await client.post(
        "/api/v1/games/mines/action",
        headers={**headers, "Idempotency-Key": "mines-reveal-repeat"},
        json={"action": "reveal", "tile_index": safe_tile},
    )
    assert repeated.status_code == 400

    bust = await client.post(
        "/api/v1/games/mines/action",
        headers={**headers, "Idempotency-Key": "mines-reveal-mine"},
        json={"action": "reveal", "tile_index": mine_tile},
    )
    assert bust.status_code == 200
    assert bust.json()["status"] == "LOST"
    assert bust.json()["server_seed"]
    cashout = await client.post(
        "/api/v1/games/mines/action",
        headers={**headers, "Idempotency-Key": "mines-cashout-after-bust"},
        json={"action": "cashout"},
    )
    assert cashout.status_code == 404

    async with mines_env["factory"]() as session:
        verified = await FairnessService(session).verify_round(round_id)
        assert verified["hash_valid"] is True
        assert verified["result_matches"] is True


def test_mines_multiplier_uses_integer_payout_basis_points():
    assert compute_mines_multiplier_bp(0, 3) == 100
    assert compute_mines_multiplier_bp(1, 3) == 110
    assert compute_mines_multiplier_bp(2, 3) == 125


@pytest.mark.asyncio
async def test_bet_history_never_reveals_live_mine_positions(mines_env):
    """Regression: /history/bets used to return the hidden mine layout mid-game."""
    client, headers = mines_env["client"], mines_env["headers"]
    start = await client.post(
        "/api/v1/games/mines/action",
        headers={**headers, "Idempotency-Key": "history-leak-start"},
        json={"action": "start", "bet_amount": 1_000, "mine_count": 3},
    )
    assert start.status_code == 200

    history = await client.get("/api/v1/history/bets", params={"game_id": "mines"}, headers=headers)
    assert history.status_code == 200
    [item] = history.json()["items"]
    assert item["status"] == "PLACED"
    assert "mines" not in (item["selection"] or {})

    active = await client.get("/api/v1/games/mines/active", headers=headers)
    assert active.status_code == 200 and active.json()["mines"] is None
