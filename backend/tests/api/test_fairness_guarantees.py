"""Provably-fair guarantees: no API reveals a live round's seed; finished rounds verify."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.constants import PermissionCode
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.games.wingo.rules import compute_outcome
from app.main import create_app
from app.models.game import Game, GameEntry, GameRound, GameSetting
from app.models.role import Permission, Role, RolePermission
from app.models.user import User
from app.utils.rng import hash_server_seed

SEED = "a" * 64


@pytest.fixture
async def env(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add_all([Role(id=1, name="USER"), Role(id=3, name="SUPERADMIN")])
        perms = [Permission(id=i + 1, code=c.value, name=c.value) for i, c in enumerate(PermissionCode)]
        s.add_all(perms)
        await s.flush()
        s.add_all([RolePermission(role_id=3, permission_id=p.id) for p in perms])
        s.add_all([
            User(id="sa", username="sa", email="sa@x.io", password_hash="x", role_id=3, is_active=True, totp_enabled=True, two_factor_method="email"),
            User(id="p1", username="p1", email="p1@x.io", password_hash="x", role_id=1, is_active=True),
            Game(id="wingo_30s", name="WinGo", type="COLOR", is_active=True),
            Game(id="mines", name="Mines", type="MINES", is_active=True),
            GameSetting(game_id="wingo_30s", min_bet=100, max_bet=10_000),
            GameSetting(game_id="mines", min_bet=100, max_bet=10_000),
        ])
        outcome = compute_outcome(SEED, "client-1", 7)
        s.add_all([
            GameRound(id="live", game_id="wingo_30s", round_no=8, status="OPEN", server_seed=SEED, server_seed_hash=hash_server_seed(SEED), client_seed="client-2"),
            GameRound(id="done", game_id="wingo_30s", round_no=7, status="HISTORY", server_seed=SEED, server_seed_hash=hash_server_seed(SEED), client_seed="client-1",
                      result={"number": outcome.number, "size": outcome.size, "colours": list(outcome.colours)}),
            GameRound(id="mround", game_id="mines", round_no=1, status="RUNNING", server_seed=SEED, server_seed_hash=hash_server_seed(SEED), client_seed="c"),
            GameEntry(id="m1", round_id="mround", user_id="p1", bet_amount=100, payout_amount=0, status="PLACED", idempotency_key="m1",
                      selection={"mine_count": 3, "mines": [1, 2, 3], "revealed_tiles": []}),
        ])
        await s.commit()

    monkeypatch.setattr("app.api.v1.games.routes.get_redis_client", lambda: None)
    app = create_app()

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    sa = {"Authorization": f"Bearer {create_access_token({'sub': 'sa', 'role': 'SUPERADMIN'})}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield client, sa
    await engine.dispose()


@pytest.mark.asyncio
async def test_live_round_seed_never_leaks(env):
    client, sa = env
    public = await client.get("/api/v1/games/wingo_30s/history", params={"status": "OPEN"})
    assert public.status_code == 200
    assert all(item["server_seed"] is None for item in public.json()["items"])

    commitment = (await client.get("/api/v1/rounds/live/commitment")).json()
    assert commitment["server_seed"] is None and commitment["client_seed"] == "client-2"
    assert (await client.get("/api/v1/rounds/live/verify")).status_code == 403

    # Not even the super admin can read it early
    admin_view = (await client.get("/api/v1/admin/rounds/live", headers=sa)).json()
    assert admin_view["server_seed"] is None
    listing = (await client.get("/api/v1/admin/rounds", headers=sa, params={"game_id": "wingo_30s"})).json()
    assert all(r["server_seed"] is None for r in listing["items"] if r["round_id"] == "live")


@pytest.mark.asyncio
async def test_live_mines_layout_hidden_from_admins(env):
    client, sa = env
    view = (await client.get("/api/v1/admin/rounds/mround", headers=sa)).json()
    assert "mines" not in (view["entries"][0]["selection"] or {})


@pytest.mark.asyncio
async def test_finished_wingo_round_verifies(env):
    client, _ = env
    data = (await client.get("/api/v1/rounds/done/verify")).json()
    assert data["hash_valid"] is True and data["result_matches"] is True
    assert data["server_seed"] == SEED and data["nonce"] == 7


@pytest.mark.asyncio
async def test_exposure_groups_bets_by_pick(env, monkeypatch):
    """GROUP BY aggregate per pick; P/L per number is display-only maths."""
    from types import SimpleNamespace

    from app.api.v1.admin import superadmin

    class FakeState:
        def __init__(self, *_a):
            pass

        async def get_round_state(self, game_id):
            return SimpleNamespace(round_id="live", round_no=8, status="OPEN", metadata={"period": "P1"}) if game_id == "wingo_30s" else None

    monkeypatch.setattr("app.games.base.state.RedisRoundStateManager", FakeState)
    monkeypatch.setattr(superadmin, "get_redis_client", lambda: None)
    client, sa = env
    # seed bets on the live period
    from app.core.database import get_db
    app_db = client._transport.app.dependency_overrides[get_db]
    async for session in app_db():
        session.add_all([
            GameEntry(id="b1", round_id="live", user_id="p1", bet_amount=1000, status="PLACED", idempotency_key="b1", selection={"type": "NUMBER", "value": "3"}),
            GameEntry(id="b2", round_id="live", user_id="p1", bet_amount=500, status="PLACED", idempotency_key="b2", selection={"type": "NUMBER", "value": "3"}),
            GameEntry(id="b3", round_id="live", user_id="p1", bet_amount=2000, status="PLACED", idempotency_key="b3", selection={"type": "SIZE", "value": "BIG"}),
        ])
        await session.commit()

    data = (await client.get("/api/v1/admin/risk/live", headers=sa)).json()
    wingo = next(w for w in data["wingo"] if w["game_id"] == "wingo_30s")
    assert wingo["by_pick"]["NUMBER:3"] == {"count": 2, "amount": 1500}
    three = wingo["outcomes"][3]
    assert three["bets"] == 2 and three["staked"] == 1500
    assert three["payout"] == 1500 * 9 and three["house_net"] == 3500 - 13500
    seven = wingo["outcomes"][7]  # BIG wins at 1.96x
    assert seven["payout"] == 2000 * 196 // 100
