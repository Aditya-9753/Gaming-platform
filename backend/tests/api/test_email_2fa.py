"""Admin two-step verification by emailed one-time code."""

from __future__ import annotations

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import create_app
from app.models.role import Role
from app.models.user import User
from app.services.email_service import EmailServiceInterface

PASSWORD = "AdminPass123!"


class CaptureEmail(EmailServiceInterface):
    def __init__(self) -> None:
        self.codes: list[tuple[str, str]] = []

    async def send(self, to_email, subject, text, html_body=None):  # pragma: no cover - unused
        pass

    async def send_otp_email(self, to_email: str, code: str, purpose: str = "login") -> None:
        self.codes.append((to_email, code))


@pytest.fixture
async def env(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(Role(id=2, name="ADMIN"))
        session.add(User(id="adm", username="boss", email="boss@example.com", password_hash=hash_password(PASSWORD), role_id=2, is_active=True))
        await session.commit()

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mail = CaptureEmail()
    monkeypatch.setattr("app.services.email_otp_service.get_redis_client", lambda: redis)
    monkeypatch.setattr("app.services.email_otp_service.get_email_service", lambda: mail)

    app = create_app()

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, mail
    await engine.dispose()


async def _login(client, code=None):
    return await client.post("/api/v1/auth/login", json={"username": "boss", "password": PASSWORD, "totp_code": code})


@pytest.mark.asyncio
async def test_email_2fa_setup_and_login(env):
    client, mail = env
    first = await _login(client)
    assert first.status_code == 200
    headers = {"Authorization": f"Bearer {first.json()['access_token']}"}
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["requires_2fa_setup"] is True

    sent = await client.post("/api/v1/auth/2fa/email/send", headers=headers, json={})
    assert sent.status_code == 200 and sent.json()["sent_to"].endswith("@example.com")
    to, code = mail.codes[-1]
    assert to == "boss@example.com" and len(code) == 6

    wrong = "000000" if code != "000000" else "111111"
    assert (await client.post("/api/v1/auth/2fa/email/verify", headers=headers, json={"code": wrong})).status_code == 401
    ok = await client.post("/api/v1/auth/2fa/email/verify", headers=headers, json={"code": code})
    assert ok.status_code == 200 and ok.json()["method"] == "email"
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert me["requires_2fa_setup"] is False and me["two_factor_method"] == "email"

    # Every sign-in now needs a freshly emailed code
    challenge = await _login(client)
    assert challenge.status_code == 401
    assert "Verification code sent" in challenge.json()["error"]["message"]
    login_code = mail.codes[-1][1]
    assert (await _login(client, "999999" if login_code != "999999" else "888888")).status_code == 401
    assert (await _login(client, login_code)).status_code == 200
    # single use
    assert (await _login(client, login_code)).status_code == 401


@pytest.mark.asyncio
async def test_codes_only_go_to_allowed_admin_emails(env, monkeypatch):
    client, mail = env
    token = (await _login(client)).json()["access_token"]
    monkeypatch.setattr(get_settings(), "ADMIN_OTP_EMAILS", "owner@example.com")
    blocked = await client.post("/api/v1/auth/2fa/email/send", headers={"Authorization": f"Bearer {token}"}, json={})
    assert blocked.status_code == 403
    allowed = await client.post("/api/v1/auth/2fa/email/send", headers={"Authorization": f"Bearer {token}"}, json={"email": "owner@example.com"})
    assert allowed.status_code == 200 and mail.codes[-1][0] == "owner@example.com"
