"""Super admin Aviator speed page: only the super admin can change the flight speed."""

from __future__ import annotations

import math

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.constants import ROLE_PERMISSIONS, PermissionCode, UserRole
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import create_app
from app.models.game import Game, GameSetting
from app.models.role import Permission, Role, RolePermission
from app.models.user import User

SECRET = pyotp.random_base32()


@pytest.fixture
async def env(monkeypatch):
    import fakeredis

    from app.core import redis as redis_module

    monkeypatch.setattr(redis_module, "redis_client", fakeredis.aioredis.FakeRedis(decode_responses=True))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add_all([Role(id=1, name=UserRole.ADMIN.value), Role(id=2, name=UserRole.SUPERADMIN.value)])
        perms = {c: Permission(id=n + 1, code=c.value, name=c.value) for n, c in enumerate(PermissionCode)}
        s.add_all(perms.values())
        await s.flush()
        s.add_all([RolePermission(role_id=1, permission_id=perms[c].id) for c in ROLE_PERMISSIONS[UserRole.ADMIN]])
        for uid, rid in (("admin", 1), ("super", 2)):
            s.add(User(id=uid, username=uid, email=f"{uid}@x.io", password_hash="x", role_id=rid, is_active=True,
                       totp_enabled=True, totp_secret=SECRET, two_factor_method="totp"))
        s.add(Game(id="aviator", name="Aviator", type="CRASH", description="x", is_active=True))
        s.add(GameSetting(game_id="aviator", min_bet=100, max_bet=500000, house_edge_percent=300,
                          config={"betting_duration_sec": 6, "exp_growth_rate": 0.09, "growth_model": "exponential"}))
        await s.commit()
    app = create_app()

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    auth = lambda uid, role: {"Authorization": f"Bearer {create_access_token({'sub': uid, 'role': role})}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c, auth("super", "SUPERADMIN"), auth("admin", "ADMIN")
    await engine.dispose()


async def test_super_admin_controls_aviator_speed(env):
    client, sa, admin = env
    view = (await client.get("/api/v1/admin/aviator/speed", headers=sa)).json()
    assert view["exp_growth_rate"] == 0.09 and view["seconds_to"]["2x"] == round(math.log(2) / 0.09, 1)
    assert len(view["presets"]) >= 4

    r = await client.put("/api/v1/admin/aviator/speed", headers=sa,
                         json={"seconds_to_2x": 5, "betting_duration_sec": 5, "intermission_sec": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["exp_growth_rate"] == round(math.log(2) / 5, 4) and body["seconds_to"]["2x"] == 5.0
    assert body["betting_duration_sec"] == 5 and body["intermission_sec"] == 3

    # out-of-range values are refused
    assert (await client.put("/api/v1/admin/aviator/speed", headers=sa, json={"exp_growth_rate": 5})).status_code == 400
    assert (await client.put("/api/v1/admin/aviator/speed", headers=sa, json={"betting_duration_sec": 1})).status_code == 400

    # an ordinary admin can neither read this page nor change speed through game settings
    assert (await client.get("/api/v1/admin/aviator/speed", headers=admin)).status_code == 403
    r = await client.patch("/api/v1/admin/games/aviator/settings", headers=admin, json={"config": {"exp_growth_rate": 0.3}})
    assert r.status_code == 403 and "super admin" in r.text.lower()
    # ...but the admin can still save other settings, re-sending the unchanged speed values
    current = (await client.get("/api/v1/admin/games/aviator/settings", headers=admin)).json()["config"]
    r = await client.patch("/api/v1/admin/games/aviator/settings", headers=admin, json={"config": current, "min_bet": 200})
    assert r.status_code == 200, r.text

    audit = (await client.get("/api/v1/admin/audit-logs?action=AVIATOR_SPEED_CHANGED", headers=sa)).json()
    assert "AVIATOR_SPEED_CHANGED" in str(audit)
