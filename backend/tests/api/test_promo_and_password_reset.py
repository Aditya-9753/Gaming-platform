"""No automatic sign-up bonus, bonus promo codes, one account per number, password reset by email."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.constants import ROLE_PERMISSIONS, PermissionCode, UserRole
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import create_app
from app.models.role import Permission, Role, RolePermission
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction


@pytest.fixture
async def env(monkeypatch):
    import fakeredis

    from app.core import redis as redis_module
    from app.services import platform_settings

    monkeypatch.setattr(redis_module, "redis_client", fakeredis.aioredis.FakeRedis(decode_responses=True))
    monkeypatch.setattr(platform_settings, "_cache", {})
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        roles = {r: Role(id=n + 1, name=r.value) for n, r in enumerate((UserRole.USER, UserRole.ADMIN, UserRole.SUPERADMIN))}
        s.add_all(roles.values())
        perms = {c: Permission(id=n + 1, code=c.value, name=c.value) for n, c in enumerate(PermissionCode)}
        s.add_all(perms.values())
        await s.flush()
        for role in (UserRole.USER, UserRole.ADMIN):
            s.add_all([RolePermission(role_id=roles[role].id, permission_id=perms[c].id) for c in ROLE_PERMISSIONS[role]])
        for uid, role in (("super", UserRole.SUPERADMIN), ("admin", UserRole.ADMIN)):
            s.add(User(id=uid, username=uid, email=f"{uid}@x.io", password_hash="x", role_id=roles[role].id, is_active=True,
                       totp_enabled=True, totp_secret=pyotp.random_base32(), two_factor_method="totp"))
        await s.commit()
    app = create_app()

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    auth = lambda uid, role: {"Authorization": f"Bearer {create_access_token({'sub': uid, 'role': role})}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield {"client": c, "db": factory, "super": auth("super", "SUPERADMIN"), "admin": auth("admin", "ADMIN")}
    await engine.dispose()


async def _signup(client: AsyncClient, phone: str, **extra):
    return await client.post("/api/v1/auth/register", json={"phone": phone, "password": "Player123", "age_confirmed": True, **extra})


async def _balance(env, phone: str) -> int:
    async with env["db"]() as db:
        return (await db.execute(select(Wallet.balance).join(User, User.id == Wallet.user_id).where(User.phone == f"+91{phone}"))).scalar_one()


async def test_new_accounts_get_no_bonus_and_one_number_makes_one_account(env):
    client = env["client"]
    r = await _signup(client, "9811100001")
    assert r.status_code == 201, r.text
    assert r.json()["promo"] is None
    assert await _balance(env, "9811100001") == 0
    async with env["db"]() as db:
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one() == 0

    for same_number in ("9811100001", "+91 98111-00001", "09811100001"):
        dup = await _signup(client, same_number)
        assert dup.status_code == 409 and "already registered" in dup.text
    no_number = await client.post("/api/v1/auth/register", json={"username": "nophone_user", "password": "Player123", "age_confirmed": True})
    assert no_number.status_code == 422 and "Mobile number is required" in no_number.text


async def test_promo_codes_give_the_bonus_once_per_player_within_limits(env):
    client, sa = env["client"], env["super"]

    # only the super admin manages codes
    assert (await client.get("/api/v1/admin/promo-codes", headers=env["admin"])).status_code == 403
    r = await client.post("/api/v1/admin/promo-codes", headers=sa, json={"code": "welcome100", "amount_paise": 10000, "max_uses": 2})
    assert r.status_code == 201, r.text
    promo = r.json()
    assert promo["code"] == "WELCOME100" and promo["status"] == "ACTIVE"
    assert (await client.post("/api/v1/admin/promo-codes", headers=sa, json={"code": "WELCOME100", "amount_paise": 5000})).status_code == 409
    assert (await client.post("/api/v1/admin/promo-codes", headers=sa, json={"code": "bad code!", "amount_paise": 5000})).status_code == 400

    # code typed at sign-up: bonus credited as a ledger row
    r = await _signup(client, "9822200001", promo_code="welcome100")
    assert r.status_code == 201, r.text
    assert r.json()["promo"] == {"code": "WELCOME100", "amount_paise": 10000, "message": None}
    assert await _balance(env, "9822200001") == 10000
    first = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # the same player cannot use it twice
    again = await client.post("/api/v1/wallet/promo", headers=first, json={"code": "WELCOME100"})
    assert again.status_code == 409 and "already used" in again.text

    # a second player redeems it from the wallet; then the code is used up
    second = await _signup(client, "9822200002")
    h2 = {"Authorization": f"Bearer {second.json()['access_token']}"}
    assert (await client.post("/api/v1/wallet/promo", headers=h2, json={"code": "nope123"})).status_code == 404
    ok = await client.post("/api/v1/wallet/promo", headers=h2, json={"code": " welcome100 "})
    assert ok.status_code == 200 and ok.json()["amount_paise"] == 10000
    third = await _signup(client, "9822200003", promo_code="WELCOME100")
    assert third.status_code == 201  # a used-up code never blocks the sign-up
    assert third.json()["promo"]["amount_paise"] == 0 and "fully used" in third.json()["promo"]["message"]
    assert await _balance(env, "9822200003") == 0

    # a partner's code (not a bonus code) is accepted silently at sign-up
    partner_code = await _signup(client, "9822200004", promo_code="PARTNER77")
    assert partner_code.status_code == 201 and partner_code.json()["promo"] is None

    # pause, expiry, and who used it
    items = (await client.get("/api/v1/admin/promo-codes", headers=sa)).json()["items"]
    assert items[0]["used_count"] == 2 and items[0]["status"] == "ENDED"
    used = (await client.get(f"/api/v1/admin/promo-codes/{promo['id']}/redemptions", headers=sa)).json()["items"]
    assert sorted(u["phone"] for u in used) == ["+919822200001", "+919822200002"]

    r = await client.post("/api/v1/admin/promo-codes", headers=sa, json={"code": "DIWALI50", "amount_paise": 5000})
    diwali = r.json()
    paused = await client.patch(f"/api/v1/admin/promo-codes/{diwali['id']}", headers=sa, json={"is_active": False})
    assert paused.json()["status"] == "PAUSED"
    assert "no longer active" in (await client.post("/api/v1/wallet/promo", headers=h2, json={"code": "DIWALI50"})).text
    await client.patch(f"/api/v1/admin/promo-codes/{diwali['id']}", headers=sa, json={"is_active": True})
    assert (await client.post("/api/v1/wallet/promo", headers=h2, json={"code": "DIWALI50"})).status_code == 200
    assert await _balance(env, "9822200002") == 15000
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert (await client.patch(f"/api/v1/admin/promo-codes/{diwali['id']}", headers=sa, json={"expires_at": past})).status_code == 400


async def test_forgot_password_by_mobile_number_emails_a_working_link(env):
    client = env["client"]
    assert (await _signup(client, "9833300001", email="sanu@example.com")).status_code == 201
    assert (await _signup(client, "9833300002")).status_code == 201  # no email on this one

    sent = []

    class FakeEmail:
        async def send_password_reset_email(self, to_email, link):
            sent.append((to_email, link))

    with patch("app.services.auth_service.get_email_service", return_value=FakeEmail()):
        r = await client.post("/api/v1/auth/forgot-password", json={"identifier": "+91 98333 00001"})
        assert r.status_code == 200, r.text
        assert r.json()["sent_to"] == "sa***@example.com"
        legacy = await client.post("/api/v1/auth/forgot-password", json={"email": "SANU@example.com"})
        assert legacy.status_code == 200
        unknown = await client.post("/api/v1/auth/forgot-password", json={"identifier": "9899999999"})
        assert unknown.status_code == 404 and "No account found" in unknown.text
        no_email = await client.post("/api/v1/auth/forgot-password", json={"identifier": "9833300002"})
        assert no_email.status_code == 400 and "no email address" in no_email.text

    assert len(sent) == 2 and sent[0][0] == "sanu@example.com"
    link = urlparse(sent[0][1])
    assert link.path == "/reset-password"
    token = parse_qs(link.query)["token"][0]

    # players keep the simple sign-up rule (letters + a number) when resetting
    assert (await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "onlyletters"})).status_code == 400
    r = await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "newpass2026"})
    assert r.status_code == 204, r.text
    assert (await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "other2026x"})).status_code == 400
    assert (await client.post("/api/v1/auth/login", json={"username": "9833300001", "password": "newpass2026"})).status_code == 200
    assert (await client.post("/api/v1/auth/login", json={"username": "9833300001", "password": "Player123"})).status_code == 401


async def test_staff_resets_a_number_only_players_password(env):
    client = env["client"]
    r = await _signup(client, "9844400001")  # no email: the emailed link cannot reach this player
    assert r.status_code == 201
    async with env["db"]() as db:
        uid = (await db.execute(select(User.id).where(User.phone == "+919844400001"))).scalar_one()

    reset = await client.post(f"/api/v1/admin/users/{uid}/reset-password", headers=env["admin"])
    assert reset.status_code == 200, reset.text
    temporary = reset.json()["temporary_password"]
    assert (await client.post("/api/v1/auth/login", json={"username": "9844400001", "password": "Player123"})).status_code == 401
    assert (await client.post("/api/v1/auth/login", json={"username": "9844400001", "password": temporary})).status_code == 200

    # staff accounts are not reset this way
    assert (await client.post("/api/v1/admin/users/super/reset-password", headers=env["admin"])).status_code == 403


async def test_login_with_an_unregistered_number_says_so(env):
    client = env["client"]
    r = await client.post("/api/v1/auth/login", json={"username": "9855500001", "password": "Player123"})
    assert r.status_code == 401 and "No account found with this mobile number" in r.text
    assert (await _signup(client, "9855500001")).status_code == 201
    wrong = await client.post("/api/v1/auth/login", json={"username": "9855500001", "password": "Wrong12345"})
    assert wrong.status_code == 401 and "Invalid username or password" in wrong.text
    assert (await client.post("/api/v1/auth/login", json={"username": "9855500001", "password": "Player123"})).status_code == 200


async def test_admin_panel_is_operations_only(env):
    """Admins do day-to-day work; money, profit, game settings, ledgers and partner finance are super-admin only."""
    client, admin, sa = env["client"], env["admin"], env["super"]
    r = await _signup(client, "9866600001")
    async with env["db"]() as db:
        uid = (await db.execute(select(User.id).where(User.phone == "+919866600001"))).scalar_one()

    super_only = [
        ("GET", "/api/v1/admin/dashboard/live", None),
        ("GET", "/api/v1/admin/reports/live", None),
        ("GET", "/api/v1/admin/audit-logs", None),
        ("POST", f"/api/v1/admin/users/{uid}/adjust-balance", {"amount_paise": 10000, "reason": "test credit", "type": "credit"}),
        ("GET", "/api/v1/aff/admin/wallets", None),
    ]
    for method, path, body in super_only:
        res = await client.request(method, path, headers=admin, json=body)
        assert res.status_code == 403, (path, res.status_code, res.text[:120])

    for path in ("/api/v1/admin/users", f"/api/v1/admin/users/{uid}", "/api/v1/admin/payments/summary", "/api/v1/aff/admin/partners"):
        res = await client.get(path, headers=admin)
        assert res.status_code == 200, (path, res.status_code, res.text[:120])
    assert (await client.get("/api/v1/admin/audit-logs", headers=sa)).status_code == 200
