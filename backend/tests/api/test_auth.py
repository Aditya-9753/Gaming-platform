"""Integration tests for auth endpoints.

Uses an in-memory SQLite engine (aiosqlite) and a real AsyncClient
via ASGITransport, so no live Postgres or Redis is required.
"""

from __future__ import annotations

from typing import AsyncGenerator, Optional
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.constants import UserRole
from app.core.database import Base, get_db
from app.main import create_app

# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def engine():
    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture(scope="function")
async def session_factory(engine):
    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    return factory


def _build_redis_mock() -> tuple[AsyncMock, dict]:
    """Return (redis_mock, shared_store) so tests can inspect/mutate the store."""
    store: dict = {}

    async def mock_incr(key):
        store[key] = store.get(key, 0) + 1
        return store[key]

    async def mock_expire(key, seconds):
        pass  # no-op in tests

    async def mock_get(key):
        return store.get(key)

    async def mock_set(key, value, ex=None):
        store[key] = value

    async def mock_delete(*keys):
        for k in keys:
            store.pop(k, None)

    async def mock_ttl(key):
        return -1  # never locked

    async def mock_ping():
        return True

    redis_mock = AsyncMock()
    redis_mock.incr = mock_incr
    redis_mock.expire = mock_expire
    redis_mock.get = mock_get
    redis_mock.set = mock_set
    redis_mock.delete = mock_delete
    redis_mock.ttl = mock_ttl
    redis_mock.ping = mock_ping
    return redis_mock, store


@pytest.fixture(scope="function")
async def client(session_factory, engine) -> AsyncGenerator[AsyncClient, None]:
    """ASGI test client backed by in-memory SQLite and mocked Redis."""
    from scripts.seed_db import (
        seed_games,
        seed_roles_and_permissions,
        seed_system_settings,
    )

    # Seed in a dedicated session
    async with session_factory() as seed_sess:
        await seed_roles_and_permissions(seed_sess)
        await seed_games(seed_sess)
        await seed_system_settings(seed_sess)

    app = create_app()

    # Override the DB dependency to use in-memory SQLite
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db

    redis_mock, _store = _build_redis_mock()

    with patch("app.core.rate_limit.get_redis_client", return_value=redis_mock), \
         patch("app.core.redis.get_redis_client", return_value=redis_mock):
        transport = ASGITransport(app=app)
        # follow_redirects + cookie-jar enabled automatically by AsyncClient
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

VALID_USER = {
    "phone": "9000000001",
    "username": "testplayer",
    "email": "player@test.com",
    "password": "TestPass@2026",
    "age_confirmed": True,
}


def _extract_cookie(response, name: str) -> Optional[str]:
    """Extract a named cookie value from a response, regardless of path."""
    # httpx stores Set-Cookie values; try response.cookies first, then headers
    value = response.cookies.get(name)
    if value:
        return value
    # Fallback: parse Set-Cookie header manually
    for header_val in response.headers.get_list("set-cookie"):
        if header_val.startswith(f"{name}="):
            return header_val.split(";")[0].split("=", 1)[1]
    return None


async def _register(client: AsyncClient, user: dict = VALID_USER) -> tuple[str, str]:
    """Register a user, return (access_token, raw_refresh_cookie_value)."""
    resp = await client.post("/api/v1/auth/register", json=user)
    assert resp.status_code == 201, resp.text
    access_token = resp.json()["access_token"]
    cookie = _extract_cookie(resp, "refresh_token")
    assert cookie is not None, "refresh_token cookie missing from register response"
    return access_token, cookie


# =========================================================================
# Tests
# =========================================================================

@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json=VALID_USER)
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    cookie = _extract_cookie(resp, "refresh_token")
    assert cookie is not None, "Expected refresh_token cookie"


@pytest.mark.asyncio
async def test_register_age_confirmation_required(client: AsyncClient):
    payload = {**VALID_USER, "age_confirmed": False}
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    await client.post("/api/v1/auth/register", json=VALID_USER)
    resp = await client.post(
        "/api/v1/auth/register",
        json={**VALID_USER, "username": "other_user", "phone": "9000000002"},
    )
    assert resp.status_code == 409
    assert "Email" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient):
    await client.post("/api/v1/auth/register", json=VALID_USER)
    resp = await client.post(
        "/api/v1/auth/register",
        json={**VALID_USER, "email": "other@test.com", "phone": "9000000002"},
    )
    assert resp.status_code == 409
    assert "Username" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    payload = {**VALID_USER, "password": "weakpass"}
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 422, resp.text
    error = resp.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["loc"] == ["body", "password"]
    assert "letter and a number" in error["details"][0]["msg"]


@pytest.mark.asyncio
async def test_register_invalid_username_reports_field(client: AsyncClient):
    payload = {**VALID_USER, "username": "test player"}
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 422
    assert resp.json()["error"]["details"][0]["loc"] == ["body", "username"]


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post("/api/v1/auth/register", json=VALID_USER)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()
    cookie = _extract_cookie(resp, "refresh_token")
    assert cookie is not None


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/v1/auth/register", json=VALID_USER)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": VALID_USER["email"], "password": "Wrong@Pass999"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_without_totp_can_login_only_to_complete_setup(
    client: AsyncClient, session_factory
):
    from sqlalchemy import select
    from app.core.security import hash_password
    from app.models.role import Role
    from app.models.user import User

    async with session_factory() as session:
        role = (
            await session.execute(select(Role).where(Role.name == UserRole.SUPERADMIN.value))
        ).scalar_one()
        session.add(
            User(
                id="setup-admin",
                username="setupadmin",
                email="setup-admin@test.com",
                password_hash=hash_password("AdminPass@2026"),
                role_id=role.id,
                is_active=True,
                is_verified=True,
                totp_enabled=False,
            )
        )
        await session.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "setup-admin@test.com", "password": "AdminPass@2026"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["totp_enabled"] is False

    blocked_admin_api = await client.get(
        "/api/v1/admin/dashboard/stats", headers=headers
    )
    assert blocked_admin_api.status_code == 403

    setup = await client.post("/api/v1/auth/totp/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    import pyotp

    verify = await client.post(
        "/api/v1/auth/totp/verify",
        headers=headers,
        json={"code": pyotp.TOTP(setup.json()["secret"]).now()},
    )
    assert verify.status_code == 204

    enabled_me = await client.get("/api/v1/auth/me", headers=headers)
    assert enabled_me.json()["totp_enabled"] is True
    enabled_admin_api = await client.get(
        "/api/v1/admin/dashboard/stats", headers=headers
    )
    assert enabled_admin_api.status_code == 200


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient):
    access_token, _ = await _register(client)
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == VALID_USER["username"]
    assert body["role"] == UserRole.USER.value


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_rotation(client: AsyncClient):
    """New access token and new cookie on refresh; old cookie is revoked."""
    access_token, old_cookie = await _register(client)

    # Perform refresh — send cookie in header form since path restriction may
    # prevent httpx from auto-including it
    resp = await client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"refresh_token={old_cookie}"},
    )
    assert resp.status_code == 200, resp.text
    new_access = resp.json()["access_token"]
    new_cookie = _extract_cookie(resp, "refresh_token")

    # Refresh cookie must have rotated (even if access JWT looks identical within same second)
    assert new_cookie is not None
    assert new_cookie != old_cookie

    # New access token is valid for /me (whether or not the bytes differ)
    me_resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {new_access}"},
    )
    assert me_resp.status_code == 200


@pytest.mark.asyncio
async def test_refresh_token_reuse_detection(client: AsyncClient):
    """Using a revoked (already-rotated) refresh token must revoke the whole family."""
    _access, old_cookie = await _register(client)

    # First refresh — consumes old_cookie, issues new pair
    resp1 = await client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"refresh_token={old_cookie}"},
    )
    assert resp1.status_code == 200
    new_cookie = _extract_cookie(resp1, "refresh_token")

    # Reuse the now-revoked old_cookie after the short concurrency window — detected as theft
    from unittest.mock import AsyncMock, patch as _patch

    from app.services.auth_service import AuthService

    with _patch.object(AuthService, "_recently_rotated", AsyncMock(return_value=False)):
        resp2 = await client.post(
            "/api/v1/auth/refresh",
            headers={"Cookie": f"refresh_token={old_cookie}"},
        )
    assert resp2.status_code == 401
    body = resp2.json()["error"]["message"].lower()
    assert "revoked" in body or "used" in body or "session" in body

    # The sibling token from resp1 must also be revoked now (family revocation)
    if new_cookie:
        resp3 = await client.post(
            "/api/v1/auth/refresh",
            headers={"Cookie": f"refresh_token={new_cookie}"},
        )
        assert resp3.status_code == 401


@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_no_session(client: AsyncClient):
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 204
    assert not response.content


@pytest.mark.asyncio
async def test_logout(client: AsyncClient):
    access_token, cookie = await _register(client)

    logout_resp = await client.post(
        "/api/v1/auth/logout",
        headers={"Cookie": f"refresh_token={cookie}"},
    )
    assert logout_resp.status_code == 204

    # After logout the old cookie must fail
    after_resp = await client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"refresh_token={cookie}"},
    )
    assert after_resp.status_code == 401


@pytest.mark.asyncio
async def test_require_permission_factory_is_callable(client: AsyncClient):
    """require_permission factory must return a callable dependency."""
    from app.core.constants import PermissionCode
    from app.core.deps import require_permission

    checker = require_permission(PermissionCode.AUDIT_READ)
    assert callable(checker)


@pytest.mark.asyncio
async def test_forgot_password_unknown_account_says_so(client: AsyncClient):
    """Sign-up already reveals whether a number/email is registered, so the reset page says it plainly."""
    resp = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nobody@nowhere.example"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_totp_setup_and_verify(client: AsyncClient):
    """TOTP setup → verify → /me shows totp_enabled=True."""
    import pyotp

    access_token, _ = await _register(client)
    headers = {"Authorization": f"Bearer {access_token}"}

    # Setup
    setup_resp = await client.post("/api/v1/auth/totp/setup", headers=headers)
    assert setup_resp.status_code == 200, setup_resp.text
    body = setup_resp.json()
    assert "secret" in body
    secret = body["secret"]

    # Generate a valid TOTP code
    code = pyotp.TOTP(secret).now()

    # Verify → enables 2FA
    verify_resp = await client.post(
        "/api/v1/auth/totp/verify",
        json={"code": code},
        headers=headers,
    )
    assert verify_resp.status_code == 204, verify_resp.text

    # Confirm flag in /me
    me_resp = await client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["totp_enabled"] is True


@pytest.mark.asyncio
async def test_register_accepts_simple_player_passwords(client: AsyncClient):
    # Registration is rate limited per client, so check the rule on the schema
    # and send just two real requests.
    from pydantic import ValidationError

    from app.schemas.auth import RegisterRequest

    for password in ["sanukhan27", "Sanu.1234", "Sanu@123", "my pass 9"]:
        RegisterRequest(phone="9000000003", username="Sanu_x", password=password, age_confirmed=True)
    for password in ["sanukhan", "12345678", "abc12"]:
        with pytest.raises(ValidationError):
            RegisterRequest(phone="9000000003", username="Sanu_x", password=password, age_confirmed=True)
    resp = await client.post("/api/v1/auth/register", json={"phone": "9000000004", "username": "Sanukhan_27", "password": "Sanu.1234", "age_confirmed": True})
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_username_available_suggests_free_names(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={"phone": "9000000004", "username": "Sanukhan_27", "password": "sanukhan27", "age_confirmed": True})
    taken = (await client.get("/api/v1/auth/username-available", params={"username": "sanukhan_27"})).json()
    assert taken["available"] is False and len(taken["suggestions"]) == 3
    for name in taken["suggestions"]:
        assert (await client.get("/api/v1/auth/username-available", params={"username": name})).json()["available"] is True
    bad = (await client.get("/api/v1/auth/username-available", params={"username": "sanu khan"})).json()
    assert bad["available"] is False and "letters" in bad["reason"]


@pytest.mark.asyncio
async def test_register_and_sign_in_with_mobile_number(client: AsyncClient):
    """Players sign up with a mobile number (no username needed) and sign in with it in any common format."""
    resp = await client.post("/api/v1/auth/register", json={"phone": "98765 43210", "password": "Mobile1234", "age_confirmed": True})
    assert resp.status_code == 201, resp.text
    me = (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {resp.json()['access_token']}"})).json()
    assert me["phone"] == "+919876543210" and me["username"] == "9876543210"  # staff see the number; public feeds mask it

    for typed in ("9876543210", "+91 98765-43210", "09876543210"):
        login = await client.post("/api/v1/auth/login", json={"username": typed, "password": "Mobile1234"})
        assert login.status_code == 200, (typed, login.text)
    assert (await client.post("/api/v1/auth/login", json={"username": "9876543210", "password": "Wrong12345"})).status_code == 401

    # one account per number; invalid numbers and missing number are refused with a clear message
    dup = await client.post("/api/v1/auth/register", json={"phone": "+919876543210", "password": "Mobile1234", "age_confirmed": True})
    assert dup.status_code == 409 and "already registered" in dup.text
    bad = await client.post("/api/v1/auth/register", json={"phone": "12345", "password": "Mobile1234", "age_confirmed": True})
    assert bad.status_code == 422 and "mobile number" in bad.text.lower()
    none = await client.post("/api/v1/auth/register", json={"password": "Mobile1234", "age_confirmed": True})
    assert none.status_code == 422 and "Mobile number is required" in none.text


@pytest.mark.asyncio
async def test_existing_player_adds_mobile_number_then_signs_in_with_it(client: AsyncClient):
    token, _ = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.put("/api/v1/users/me", headers=headers, json={"phone": "8123456789"})
    assert r.status_code == 200, r.text
    assert r.json()["phone"] == "+918123456789"
    login = await client.post("/api/v1/auth/login", json={"username": "8123456789", "password": VALID_USER["password"]})
    assert login.status_code == 200, login.text
    # the old username still works
    assert (await client.post("/api/v1/auth/login", json={"username": VALID_USER["username"], "password": VALID_USER["password"]})).status_code == 200


@pytest.mark.asyncio
async def test_refresh_returns_the_profile_so_the_app_needs_one_round_trip(client: AsyncClient):
    _token, cookie = await _register(client)
    client.cookies.set("refresh_token", cookie, path="/api/v1/auth")
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"] and body["user"]["username"] == VALID_USER["username"] and body["user"]["role"] == "USER"
    me = (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})).json()
    assert body["user"] == me


@pytest.mark.asyncio
async def test_concurrent_refresh_with_the_same_token_does_not_sign_out(client: AsyncClient):
    """Two tabs / a quick reload send the same refresh token at once: the late request gets a fresh
    token instead of revoking the whole session. After log-out-everywhere the window does not help."""
    _access, cookie = await _register(client)
    first = await client.post("/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={cookie}"})
    late = await client.post("/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={cookie}"})
    assert first.status_code == 200 and late.status_code == 200, late.text
    newest = _extract_cookie(late, "refresh_token")
    assert (await client.post("/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={newest}"})).status_code == 200

    # log out everywhere: even inside the window the old token must not bring the session back
    token = first.json()["access_token"]
    assert (await client.post("/api/v1/auth/logout-all", headers={"Authorization": f"Bearer {token}"})).status_code in (200, 204)
    assert (await client.post("/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={cookie}"})).status_code == 401
