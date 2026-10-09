"""Access-control sweep: every endpoint is called without a token and with a plain player token.

Only an explicit allow-list of public endpoints may answer without a login, and no admin /
partner endpoint may answer a player. Catches a route added without its auth dependency.
"""

from __future__ import annotations

import re

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import rate_limit
from app.core.constants import ROLE_PERMISSIONS, PermissionCode, UserRole
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import create_app
from app.models.role import Permission, Role, RolePermission
from app.models.user import User

# Endpoints that are public on purpose (method, path template)
PUBLIC = {
    ("GET", "/"), ("GET", "/health"), ("GET", "/health/live"), ("GET", "/api/v1/health"), ("GET", "/api/v1/health/live"),
    ("GET", "/r/{code}"),
    ("POST", "/api/v1/auth/register"), ("GET", "/api/v1/auth/username-available"), ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"), ("POST", "/api/v1/auth/logout"), ("POST", "/api/v1/auth/forgot-password"),
    ("POST", "/api/v1/auth/reset-password"),
    ("GET", "/api/v1/games"), ("GET", "/api/v1/games/live/players"), ("GET", "/api/v1/games/{game_id}"),
    ("GET", "/api/v1/games/{game_id}/round"), ("GET", "/api/v1/games/{game_id}/rounds"), ("GET", "/api/v1/games/{game_id}/history"),
    ("GET", "/api/v1/games/wingo/modes"), ("GET", "/api/v1/games/cricket/matches"), ("GET", "/api/v1/games/cricket/matches/{match_id}"),
    ("GET", "/api/v1/games/cricket/matches/{match_id}/live-score"),
    # provably fair verification is public by design
    ("GET", "/api/v1/rounds/{round_id}/commitment"), ("GET", "/api/v1/rounds/{round_id}/verify"),
    ("GET", "/api/v1/leaderboard"), ("GET", "/api/v1/leaderboard/recent-wins"),
    ("GET", "/api/v1/payments/config"), ("POST", "/api/v1/payments/webhook/{provider}"),
    ("GET", "/api/v1/system/config"),
    ("POST", "/api/v1/aff/track/click"), ("GET", "/api/v1/aff/public/config"), ("GET", "/api/v1/aff/public/terms"),
    ("GET", "/api/v1/aff/public/inviter/{code}"), ("POST", "/api/v1/aff/auth/signup"), ("POST", "/api/v1/aff/auth/verify-email"),
    # HMAC-signed instead of a login
    ("POST", "/api/v1/ingest/registration"), ("POST", "/api/v1/ingest/deposit"), ("POST", "/api/v1/ingest/revenue"),
    ("POST", "/api/v1/ingest/reversal"),
}
DENIED = {401, 403}


@pytest.fixture
async def client(monkeypatch):
    import fakeredis

    from app.core import redis as redis_module

    monkeypatch.setattr(redis_module, "redis_client", fakeredis.aioredis.FakeRedis(decode_responses=True))
    rate_limit._memory_store.clear()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add(Role(id=1, name=UserRole.USER.value))
        perms = {c: Permission(id=n + 1, code=c.value, name=c.value) for n, c in enumerate(PermissionCode)}
        s.add_all(perms.values())
        await s.flush()
        s.add_all([RolePermission(role_id=1, permission_id=perms[c].id) for c in ROLE_PERMISSIONS[UserRole.USER]])
        s.add(User(id="player", username="player", email="p@x.io", password_hash="x", role_id=1, is_active=True))
        await s.commit()
    app = create_app()

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.app = app
        yield c
    await engine.dispose()


def _routes(app):
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            yield method.upper(), path


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


async def test_every_private_endpoint_requires_login(client):
    leaks = []
    for method, path in _routes(client.app):
        if (method, path) in PUBLIC:
            continue
        r = await client.request(method, _concrete(path), json={})
        if r.status_code not in DENIED:
            leaks.append(f"{method} {path} -> {r.status_code}")
    assert not leaks, "Endpoints answering without a login:\n" + "\n".join(leaks)


async def test_admin_and_partner_endpoints_refuse_players(client):
    token = {"Authorization": f"Bearer {create_access_token({'sub': 'player', 'role': 'USER'})}"}
    leaks = []
    for method, path in _routes(client.app):
        if not re.match(r"^/api/v1/(admin|aff/admin|aff/(?!public|track|auth/signup|auth/verify))|^/api/v1/risk", path):
            continue
        r = await client.request(method, _concrete(path), json={}, headers=token)
        if r.status_code not in DENIED:
            leaks.append(f"{method} {path} -> {r.status_code}")
    assert not leaks, "Staff / partner endpoints answering a player:\n" + "\n".join(leaks)
