"""Security hardening: CSRF, uploads, headers, default credentials, rate limiting, logs, JWT, SSRF."""

from __future__ import annotations

import base64

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.core import rate_limit
from app.core.config import Settings, get_settings
from app.core.exceptions import BadRequestException
from app.core.logging import _redact
from app.main import create_app
from app.middleware.csrf import CSRFOriginMiddleware
from app.middleware.global_rate_limit import GlobalRateLimitMiddleware
from app.security.uploads import validate_image_data_url

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    import fakeredis

    from app.core import redis as redis_module

    monkeypatch.setattr(redis_module, "redis_client", fakeredis.aioredis.FakeRedis(decode_responses=True))


def _data_url(kind: str, raw: bytes) -> str:
    return f"data:image/{kind};base64,{base64.b64encode(raw).decode()}"


def _echo_app(middleware, **kw):
    async def ok(_request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/x", ok, methods=["GET", "POST"])])
    return middleware(app, **kw)


# ---------------------------------------------------------------- CSRF


@pytest.mark.parametrize("headers,expected", [
    ({"cookie": "refresh_token=abc", "origin": "https://evil.example"}, 403),
    ({"cookie": "refresh_token=abc", "origin": "null"}, 403),
    ({"cookie": "refresh_token=abc", "referer": "https://evil.example/page"}, 403),
    ({"cookie": "refresh_token=abc", "origin": "https://app.example"}, 200),
    ({"cookie": "refresh_token=abc"}, 200),                         # non-browser client
    ({"origin": "https://evil.example"}, 200),                      # no cookies: nothing to forge
])
async def test_csrf_origin_check(headers, expected):
    app = _echo_app(CSRFOriginMiddleware, allowed_origins=["https://app.example"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://api.test") as c:
        assert (await c.post("/x", headers=headers)).status_code == expected
        assert (await c.get("/x", headers=headers)).status_code == 200  # safe methods untouched


# ---------------------------------------------------------------- uploads


def test_image_upload_checks_real_bytes():
    assert validate_image_data_url(_data_url("png", PNG)).startswith("data:image/png;base64,")
    with pytest.raises(BadRequestException):
        validate_image_data_url(_data_url("png", b"<script>alert(1)</script>"))  # wrong magic bytes
    with pytest.raises(BadRequestException):
        validate_image_data_url("data:image/svg+xml;base64," + base64.b64encode(b"<svg onload=alert(1)>").decode())
    with pytest.raises(BadRequestException):
        validate_image_data_url("data:image/png;base64,@@@notbase64@@@")
    with pytest.raises(BadRequestException):
        validate_image_data_url(_data_url("png", PNG + b"\x00" * 3000), max_bytes=1024)


# ---------------------------------------------------------------- headers / CORS


async def test_security_headers_and_strict_cors():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/health")
        assert r.headers["x-frame-options"] == "DENY"
        assert "default-src 'none'" in r.headers["content-security-policy"]
        assert r.headers["x-content-type-options"] == "nosniff"
        pre = await c.options("/api/v1/auth/login", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
        assert "access-control-allow-origin" not in pre.headers


# ---------------------------------------------------------------- default credentials / JWT config


def test_jwt_algorithm_and_secret_rules():
    with pytest.raises(ValueError):
        Settings(JWT_ALGORITHM="none")
    strong = "x" * 40
    with pytest.raises(ValueError):
        Settings(APP_ENV="production", DEBUG=False, JWT_SECRET=strong, JWT_REFRESH_SECRET=strong, CORS_ORIGINS="https://a.example")
    with pytest.raises(ValueError):
        Settings(APP_ENV="production", DEBUG=False, JWT_SECRET=strong, JWT_REFRESH_SECRET="y" * 40, CORS_ORIGINS="*")


async def test_default_password_blocked_in_production(monkeypatch):
    from app.services import auth_service

    class _User:
        id, is_active, password_hash, role, totp_enabled = "u1", True, "h", None, False

    class _Repo:
        async def get_by_email(self, _e):
            return _User()

    monkeypatch.setattr(auth_service, "verify_password", lambda _p, _h: True)
    monkeypatch.setattr(auth_service.settings, "APP_ENV", "production")
    svc = auth_service.AuthService.__new__(auth_service.AuthService)
    svc._users = _Repo()
    from app.core.exceptions import ForbiddenException

    with pytest.raises(ForbiddenException, match="default password"):
        await svc.login("superadmin@gamingplatform.com", "SuperAdmin@123")


# ---------------------------------------------------------------- global rate limit


async def test_global_rate_limit_per_ip():
    rate_limit._memory_store.clear()
    app = _echo_app(GlobalRateLimitMiddleware, per_minute=5, writes_per_minute=2)
    async with AsyncClient(transport=ASGITransport(app=app, client=("203.0.113.9", 1)), base_url="http://t") as c:
        codes = [(await c.post("/x")).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        assert (await c.get("/x")).status_code == 200
    # a forged left-hand X-Forwarded-For entry does not create a fresh bucket
    from app.core import redis as redis_module

    await redis_module.redis_client.flushdb()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        got = [(await c.post("/x", headers={"x-forwarded-for": f"10.0.0.{n}, 198.51.100.7"})).status_code for n in range(3)]
        assert got[-1] == 429


# ---------------------------------------------------------------- logs, SSRF


def test_logs_never_contain_secrets():
    event = _redact(None, None, {
        "event": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz ?token=s3cr3t",
        "password": "hunter22", "code": "123456", "upi_id": "name@okaxis", "user_id": "u1",
    })
    assert "abcdefghijklmnop" not in event["event"] and "s3cr3t" not in event["event"]
    assert event["password"] == event["code"] == event["upi_id"] == "[redacted]"
    assert event["user_id"] == "u1"


@pytest.mark.parametrize("url", ["https://169.254.169.254/latest/meta-data", "http://127.0.0.1/", "https://localhost/",
                                 "https://10.1.2.3/", "https://example.com:8443/", "ftp://example.com/", "https://u:p@example.com/"])
async def test_ssrf_guard_blocks_internal_targets(url):
    from app.security.ssrf import assert_public_url

    with pytest.raises(BadRequestException):
        await assert_public_url(url)


def test_settings_cache_untouched():
    assert get_settings().JWT_ALGORITHM == "HS256"
