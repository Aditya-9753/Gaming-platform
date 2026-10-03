"""Super-admin risk-control API: controls, toggle, update and yield backtest."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.constants import PermissionCode
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import create_app
from app.models.game import Game, GameEntry, GameRound
from app.models.role import Permission, Role, RolePermission
from app.models.user import User


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
            User(id="sa", username="sa", email="sa@x.io", password_hash="x", role_id=3, is_active=True,
                 totp_enabled=True, two_factor_method="email"),
            User(id="p1", username="p1", email="p1@x.io", password_hash="x", role_id=1, is_active=True),
            Game(id="wingo_1m", name="WinGo 1 Min", type="COLOR", is_active=True),
            Game(id="aviator", name="Aviator", type="AVIATOR", is_active=True),
        ])
        s.add_all([
            GameRound(id="r1", game_id="wingo_1m", round_no=1, status="HISTORY", server_seed_hash="h" * 64),
            GameEntry(id="e1", round_id="r1", user_id="p1", bet_amount=1000, payout_amount=800,
                      status="WON", idempotency_key="e1"),
        ])
        await s.commit()

    app = create_app()

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    sa = {"Authorization": f"Bearer {create_access_token({'sub': 'sa', 'role': 'SUPERADMIN'})}"}
    player = {"Authorization": f"Bearer {create_access_token({'sub': 'p1', 'role': 'USER'})}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield client, sa, player
    await engine.dispose()


@pytest.mark.asyncio
async def test_controls_toggle_and_update(env):
    client, sa, _ = env

    controls = (await client.get("/api/v1/admin/risk/controls", headers=sa)).json()
    assert controls["families"]["wingo"]["status"] == "OFF"
    assert any(row["family"] == "wingo" for row in controls["matrix"])

    toggled = await client.post("/api/v1/admin/risk/controls/toggle", headers=sa,
                                json={"game": "wingo_1m", "status": "ON"})
    assert toggled.status_code == 200
    assert toggled.json()["current_mode"] == "ON"
    assert toggled.json()["family"] == "wingo"

    updated = await client.post("/api/v1/admin/risk/controls/update", headers=sa,
                                json={"family": "wingo", "changes": {"max_round_pool_paise": 5000}})
    assert updated.status_code == 200
    assert updated.json()["control"]["max_round_pool_paise"] == 5000

    bad = await client.post("/api/v1/admin/risk/controls/update", headers=sa,
                            json={"family": "wingo", "changes": {"status": "MAYBE"}})
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_yield_backtest_endpoints(env):
    client, sa, _ = env

    report = await client.post("/api/v1/admin/risk/backtest", headers=sa,
                               json={"days": 30, "max_rounds": 100})
    assert report.status_code == 200
    body = report.json()
    assert body["games"]["wingo_1m"]["hold_pct"] == 20.0
    assert body["totals"]["wagered_paise"] == 1000

    latest = await client.get("/api/v1/admin/risk/backtest/latest", headers=sa)
    assert latest.status_code == 200
    assert latest.json()["report"]["totals"]["wagered_paise"] == 1000
    assert latest.json()["history"][0]["window_days"] == 30


@pytest.mark.asyncio
async def test_risk_api_requires_superadmin(env):
    client, _, player = env
    assert (await client.get("/api/v1/admin/risk/controls", headers=player)).status_code == 403
    assert (await client.get("/api/v1/admin/risk/controls")).status_code == 401