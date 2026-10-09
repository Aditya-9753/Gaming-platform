"""Payments: deposits (auto + manual verification), withdrawals (super-admin only), controls.

Mirrors the "Mandatory Test Cases" of the payment security architecture.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import rate_limit
from app.core.config import get_settings
from app.core.constants import ROLE_PERMISSIONS, PermissionCode, UserRole
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.models.payment import Beneficiary, Deposit, Withdrawal
from app.models.role import Permission, Role, RolePermission
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.services import platform_settings

WEBHOOK_SECRET = "s3cret-test-key"
SA_SECRET = pyotp.random_base32()
A1_SECRET = pyotp.random_base32()
A2_SECRET = pyotp.random_base32()


@pytest.fixture
async def env(monkeypatch):
    rate_limit._memory_store.clear()
    rate_limit._lockout_store.clear()
    platform_settings._cache_at = 0.0
    try:
        import redis as sync_redis

        r = sync_redis.Redis.from_url(get_settings().REDIS_URL, socket_connect_timeout=1)
        for key in r.scan_iter("rl:pay:*"):
            r.delete(key)
        for key in r.scan_iter("*txnpin*"):
            r.delete(key)
    except Exception:
        pass
    monkeypatch.setattr(get_settings(), "PAYMENT_WEBHOOK_SECRETS", f"testpay:{WEBHOOK_SECRET}")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        role_ids = {UserRole.USER: 1, UserRole.ADMIN: 2, UserRole.SUPERADMIN: 3, UserRole.SUPPORT: 4}
        s.add_all([Role(id=i, name=r.value) for r, i in role_ids.items()])
        perms = {c: Permission(id=n + 1, code=c.value, name=c.value) for n, c in enumerate(PermissionCode)}
        s.add_all(perms.values())
        await s.flush()
        for role, rid in role_ids.items():
            s.add_all([RolePermission(role_id=rid, permission_id=perms[c].id) for c in ROLE_PERMISSIONS[role]])

        def staff(uid, rid, secret):
            return User(id=uid, username=uid, email=f"{uid}@x.io", password_hash="x", role_id=rid, is_active=True,
                        totp_enabled=True, totp_secret=secret, two_factor_method="totp")

        s.add_all([
            staff("sa", 3, SA_SECRET), staff("sa2", 3, SA_SECRET), staff("a1", 2, A1_SECRET), staff("a2", 2, A2_SECRET),
            User(id="sup", username="sup", email="sup@x.io", password_hash="x", role_id=4, is_active=True,
                 totp_enabled=True, totp_secret=SA_SECRET, two_factor_method="totp"),
        ])
        for uid in ("p1", "p2"):
            s.add(User(id=uid, username=uid, email=f"{uid}@x.io", password_hash=hash_password("Player@123"), role_id=1, is_active=True))
            s.add(Wallet(id=f"w-{uid}", user_id=uid, balance=0, locked_balance=0, pending_withdrawal=0))
        await s.commit()

    app = create_app()

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override

    def auth(uid, role):
        return {"Authorization": f"Bearer {create_access_token({'sub': uid, 'role': role})}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield {
            "client": client,
            "db": factory,
            "sa": auth("sa", "SUPERADMIN"), "sa2": auth("sa2", "SUPERADMIN"),
            "a1": auth("a1", "ADMIN"), "a2": auth("a2", "ADMIN"), "sup": auth("sup", "SUPPORT"),
            "p1": auth("p1", "USER"), "p2": auth("p2", "USER"),
        }
    await engine.dispose()


# ------------------------------------------------------------------ helpers


async def step(env, who, secret):
    r = await env["client"].post("/api/v1/admin/payments/step-up", headers=env[who], json={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200, r.text
    return {**env[who], "X-Step-Up-Token": r.json()["token"]}


async def make_account(env, who="sa", secret=SA_SECRET, upi="collect@okaxis"):
    headers = await step(env, who, secret)
    r = await env["client"].post("/api/v1/admin/payments/accounts", headers=headers,
                                 json={"label": f"{who} QR", "upi_id": upi, "payee_name": "Rudra Collections"})
    assert r.status_code == 201, r.text
    return r.json()


async def deposit(env, who="p1", amount=50_000, key=None):
    r = await env["client"].post("/api/v1/payments/deposits", headers={**env[who], "Idempotency-Key": key or uuid.uuid4().hex},
                                 json={"amount_paise": amount})
    assert r.status_code == 201, r.text
    return r.json()


def signed(body: dict, secret=WEBHOOK_SECRET, ts=None):
    raw = json.dumps(body).encode()
    ts = str(int(ts if ts is not None else time.time()))
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    return raw, {"X-Webhook-Timestamp": ts, "X-Webhook-Signature": sig, "Content-Type": "application/json"}


async def webhook(env, body, **kw):
    raw, headers = signed(body, **kw)
    return await env["client"].post("/api/v1/payments/webhook/testpay", content=raw, headers=headers)


async def wallet(env, uid="p1"):
    async with env["db"]() as s:
        return await s.get(Wallet, f"w-{uid}")


async def ledger(env, uid="p1"):
    async with env["db"]() as s:
        return (await s.execute(select(WalletTransaction).where(WalletTransaction.wallet_id == f"w-{uid}"))).scalars().all()


async def fund(env, uid="p1", amount=500_000):
    """Credit a player through a real deposit + webhook."""
    dep = await deposit(env, uid, amount)
    r = await webhook(env, {"event_id": uuid.uuid4().hex, "type": "payment.credit", "utr": uuid.uuid4().hex[:12].upper(),
                            "amount_paise": dep["amount_paise"], "reference": dep["reference"]})
    assert r.json()["result"].startswith("credited"), r.json()
    return dep


async def ready_to_withdraw(env, uid="p1"):
    async with env["db"]() as s:
        await platform_settings.update(s, {"withdrawal_turnover_pct": 0}, None)
        await s.commit()
    c = env["client"]
    assert (await c.post("/api/v1/payments/pin", headers=env[uid], json={"pin": "2580", "password": "Player@123"})).status_code == 204
    r = await c.post("/api/v1/payments/beneficiaries", headers=env[uid],
                     json={"method": "BANK", "holder_name": "Player One", "account_number": "123456789012", "ifsc": "HDFC0001234", "pin": "2580"})
    assert r.status_code == 201, r.text
    ben = r.json()
    async with env["db"]() as s:  # skip the 24 h cooling period
        await s.execute(update(Beneficiary).where(Beneficiary.id == ben["id"])
                        .values(cooling_until=datetime.now(timezone.utc) - timedelta(minutes=1)))
        await s.commit()
    return ben


async def withdraw(env, ben, amount=100_000, uid="p1", key=None, pin="2580"):
    return await env["client"].post(
        "/api/v1/payments/withdrawals", headers={**env[uid], "Idempotency-Key": key or uuid.uuid4().hex},
        json={"amount_paise": amount, "beneficiary_id": ben["id"], "pin": pin},
    )


# ------------------------------------------------------------------ deposits


async def test_deposit_intent_is_idempotent_and_has_qr(env):
    await make_account(env)
    key = uuid.uuid4().hex
    first = await deposit(env, key=key)
    again = await deposit(env, key=key)
    assert first["id"] == again["id"]
    assert first["status"] == "PENDING"
    assert first["amount_paise"] == 50_000  # exact amount by default
    payment = first["payment"]
    assert set(payment) == {"upi_link", "qr"}  # no UPI id, payee name, bank or uploaded QR for players
    assert "Rudra%20Collections" not in payment["upi_link"] and "pn=RudraWin" in payment["upi_link"]
    assert payment["qr"].startswith("data:image/svg+xml;base64,")
    import base64
    assert ">RudraWin</text>" in base64.b64decode(payment["qr"].split(",", 1)[1]).decode()  # brand drawn on the QR
    assert f"tn={first['reference']}" in payment["upi_link"]


async def test_signed_webhook_credits_exactly_once(env):
    await make_account(env)
    dep = await deposit(env)
    event = {"event_id": "evt-1", "type": "payment.credit", "utr": "412345678901", "amount_paise": dep["amount_paise"],
             "reference": dep["reference"], "account_vpa": "collect@okaxis"}
    for _ in range(5):
        await webhook(env, event)
    # Same bank credit re-sent under another event id: still one credit
    r = await webhook(env, {**event, "event_id": "evt-2"})
    assert "already recorded" in r.json()["result"]

    status = (await env["client"].get(f"/api/v1/payments/deposits/{dep['id']}", headers=env["p1"])).json()
    assert status["status"] == "SUCCESS"
    assert (await wallet(env)).balance == dep["amount_paise"]
    assert [t.type for t in await ledger(env)].count("DEPOSIT") == 1


async def test_bad_signature_and_stale_timestamp_rejected(env):
    await make_account(env)
    dep = await deposit(env)
    event = {"event_id": "e", "type": "payment.credit", "utr": "999988887777", "amount_paise": dep["amount_paise"], "reference": dep["reference"]}
    raw, headers = signed(event, secret="wrong")
    assert (await env["client"].post("/api/v1/payments/webhook/testpay", content=raw, headers=headers)).status_code == 401
    assert (await webhook(env, event, ts=time.time() - 3600)).status_code == 401
    assert (await wallet(env)).balance == 0


async def test_user_utr_alone_never_credits(env):
    await make_account(env)
    dep = await deposit(env)
    r = await env["client"].post(f"/api/v1/payments/deposits/{dep['id']}/utr", headers=env["p1"], json={"utr": "412300001111"})
    assert r.status_code == 200
    assert r.json()["status"] == "PENDING" and r.json()["stage"] == "Verifying your payment"
    assert (await wallet(env)).balance == 0


async def test_statement_import_matches_player_utr(env):
    acct = await make_account(env)
    dep = await deposit(env)
    await env["client"].post(f"/api/v1/payments/deposits/{dep['id']}/utr", headers=env["p1"], json={"utr": "4123 0000 2222"})
    headers = await step(env, "sa", SA_SECRET)
    r = await env["client"].post("/api/v1/admin/payments/bank-credits/import", headers=headers, json={
        "account_id": acct["id"], "lines": [{"utr": "412300002222", "amount_paise": dep["amount_paise"]}],
    })
    assert r.json()["matched"] == 1, r.text
    assert (await wallet(env)).balance == dep["amount_paise"]


async def test_statement_line_matches_by_unique_amount(env):
    async with env["db"]() as s:
        await platform_settings.update(s, {"deposit_unique_paise": True}, None)
        await s.commit()
    acct = await make_account(env)
    dep = await deposit(env)
    headers = await step(env, "sa", SA_SECRET)
    r = await env["client"].post("/api/v1/admin/payments/bank-credits/import", headers=headers, json={
        "account_id": acct["id"], "lines": [{"utr": "UTRAMOUNT001", "amount_paise": dep["amount_paise"], "remark": "UPI/P2P"}],
    })
    assert r.json()["matched_deposits"] == [dep["reference"]]


async def test_amount_mismatch_goes_to_review_then_manual_confirm(env):
    await make_account(env, "a1", A1_SECRET)
    accounts = (await env["client"].get("/api/v1/admin/payments/accounts", headers=env["sa"])).json()
    headers = await step(env, "sa", SA_SECRET)
    assert (await env["client"].post(f"/api/v1/admin/payments/accounts/{accounts[0]['id']}/review", headers=headers,
                                     json={"approve": True})).status_code == 200
    dep = await deposit(env)
    await webhook(env, {"event_id": "m1", "type": "payment.credit", "utr": "777766665555", "amount_paise": 40_000,
                        "reference": dep["reference"]})
    detail = (await env["client"].get(f"/api/v1/admin/payments/deposits/{dep['id']}", headers=env["a1"])).json()
    assert detail["state"] == "MANUAL_REVIEW"
    assert (await wallet(env)).balance == 0

    # No step-up code -> refused
    r = await env["client"].post(f"/api/v1/admin/payments/deposits/{dep['id']}/confirm", headers=env["a1"],
                                 json={"utr": "777766665555", "amount_paise": 40_000})
    assert r.status_code == 403 and r.json()["error"]["code"] == "STEP_UP_REQUIRED"
    # Another admin cannot act on a1's QR deposits (and cannot even see them)
    h2 = await step(env, "a2", A2_SECRET)
    assert (await env["client"].post(f"/api/v1/admin/payments/deposits/{dep['id']}/confirm", headers=h2,
                                     json={"utr": "777766665555", "amount_paise": 40_000})).status_code == 403
    assert (await env["client"].get("/api/v1/admin/payments/deposits", headers=env["a2"])).json()["total"] == 0

    h1 = await step(env, "a1", A1_SECRET)
    r = await env["client"].post(f"/api/v1/admin/payments/deposits/{dep['id']}/confirm", headers=h1,
                                 json={"utr": "777766665555", "amount_paise": 40_000, "note": "seen in bank app"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "SUCCESS" and r.json()["verification_method"] == "MANUAL"
    assert (await wallet(env)).balance == 40_000


async def test_manual_confirm_cannot_reuse_a_utr(env):
    await make_account(env)
    d1, d2 = await deposit(env, "p1"), await deposit(env, "p2")
    headers = await step(env, "sa", SA_SECRET)
    ok = await env["client"].post(f"/api/v1/admin/payments/deposits/{d1['id']}/confirm", headers=headers, json={"utr": "555544443333"})
    assert ok.status_code == 200
    dup = await env["client"].post(f"/api/v1/admin/payments/deposits/{d2['id']}/confirm", headers=headers, json={"utr": "555544443333"})
    assert dup.status_code == 409
    # Player 2 cannot claim the same UTR either
    r = await env["client"].post(f"/api/v1/payments/deposits/{d2['id']}/utr", headers=env["p2"], json={"utr": "555544443333"})
    assert r.status_code == 409
    assert (await wallet(env, "p2")).balance == 0


async def test_player_cannot_see_or_touch_admin_payment_apis(env):
    await make_account(env)
    dep = await deposit(env)
    c = env["client"]
    assert (await c.get("/api/v1/admin/payments/deposits", headers=env["p1"])).status_code == 403
    assert (await c.post(f"/api/v1/admin/payments/deposits/{dep['id']}/confirm", headers=env["p1"], json={"utr": "111122223333"})).status_code == 403
    assert (await c.get(f"/api/v1/payments/deposits/{dep['id']}", headers=env["p2"])).status_code == 404
    # Status cannot be sent by a client
    r = await c.post("/api/v1/payments/deposits", headers={**env["p1"], "Idempotency-Key": uuid.uuid4().hex},
                     json={"amount_paise": 50_000, "status": "SUCCESS"})
    assert r.status_code == 422


async def test_admin_qr_needs_approval_and_routing_uses_only_active(env):
    acct = await make_account(env, "a1", A1_SECRET)
    assert acct["status"] == "PENDING_APPROVAL"
    r = await env["client"].post("/api/v1/payments/deposits", headers={**env["p1"], "Idempotency-Key": uuid.uuid4().hex},
                                 json={"amount_paise": 50_000})
    assert r.status_code == 503  # no approved QR yet
    assert (await env["client"].post(f"/api/v1/admin/payments/accounts/{acct['id']}/review", headers=await step(env, "a1", A1_SECRET),
                                     json={"approve": True})).status_code == 403
    assert (await env["client"].post(f"/api/v1/admin/payments/accounts/{acct['id']}/review", headers=await step(env, "sa", SA_SECRET),
                                     json={"approve": True})).json()["status"] == "ACTIVE"
    dep = await deposit(env)
    assert "pa=collect@okaxis" in dep["payment"]["upi_link"]
    # Changing the UPI id sends an admin's QR back for approval
    r = await env["client"].patch(f"/api/v1/admin/payments/accounts/{acct['id']}", headers=await step(env, "a1", A1_SECRET),
                                  json={"upi_id": "other@okicici"})
    assert r.json()["status"] == "PENDING_APPROVAL"


async def test_expired_intent_is_rejected(env):
    await make_account(env)
    dep = await deposit(env)
    async with env["db"]() as s:
        await s.execute(update(Deposit).where(Deposit.id == dep["id"]).values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
        await s.commit()
    r = await env["client"].get(f"/api/v1/payments/deposits/{dep['id']}", headers=env["p1"])
    assert r.json()["status"] == "REJECTED" and r.json()["stage"] == "Payment window expired"


# ------------------------------------------------------------------ withdrawals


async def test_withdrawal_hold_and_super_admin_completion(env):
    await make_account(env)
    await fund(env, amount=500_000)
    ben = await ready_to_withdraw(env)
    before = (await wallet(env)).balance
    key = uuid.uuid4().hex
    r = await withdraw(env, ben, 100_000, key=key)
    assert r.status_code == 201, r.text
    wd = r.json()
    assert wd["status"] == "PENDING"
    assert (await withdraw(env, ben, 100_000, key=key)).json()["id"] == wd["id"]  # double-click safe
    w = await wallet(env)
    assert (w.balance, w.pending_withdrawal) == (before - 100_000, 100_000)
    assert "WITHDRAWAL_HOLD" in [t.type for t in await ledger(env)]

    c = env["client"]
    path = f"/api/v1/admin/payments/withdrawals/{wd['id']}/complete"
    body = {"payout_reference": "NEFTPAY00001"}
    assert (await c.post(path, headers=await step(env, "a1", A1_SECRET), json=body)).status_code == 403  # admin
    assert (await c.post(path, headers=env["sup"], json=body)).status_code == 403  # support
    assert (await c.post(path, headers=env["p1"], json=body)).status_code == 403  # player
    no_mfa = await c.post(path, headers=env["sa"], json=body)
    assert no_mfa.status_code == 403 and no_mfa.json()["error"]["code"] == "STEP_UP_REQUIRED"

    done = await c.post(path, headers=await step(env, "sa", SA_SECRET), json=body)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "COMPLETED"
    w = await wallet(env)
    assert (w.balance, w.pending_withdrawal) == (before - 100_000, 0)
    assert "WITHDRAWAL_SETTLE" in [t.type for t in await ledger(env)]
    # Terminal: cannot be completed or rejected again
    assert (await c.post(path, headers=await step(env, "sa", SA_SECRET), json={"payout_reference": "NEFTPAY00002"})).status_code == 409
    mine = (await c.get(f"/api/v1/payments/withdrawals/{wd['id']}", headers=env["p1"])).json()
    assert mine["status"] == "COMPLETED" and mine["payout_reference"] == "…0001"


async def test_payout_reference_is_unique_and_reject_releases_once(env):
    await make_account(env)
    await fund(env, amount=500_000)
    ben = await ready_to_withdraw(env)
    w1 = (await withdraw(env, ben, 50_000)).json()
    w2 = (await withdraw(env, ben, 60_000)).json()
    c = env["client"]
    h = await step(env, "sa", SA_SECRET)
    assert (await c.post(f"/api/v1/admin/payments/withdrawals/{w1['id']}/complete", headers=h, json={"payout_reference": "IMPS12345678"})).status_code == 200
    assert (await c.post(f"/api/v1/admin/payments/withdrawals/{w2['id']}/complete", headers=h, json={"payout_reference": "IMPS12345678"})).status_code == 409

    balance = (await wallet(env)).balance
    rej = await c.post(f"/api/v1/admin/payments/withdrawals/{w2['id']}/reject", headers=h, json={"reason": "Name mismatch"})
    assert rej.status_code == 200 and rej.json()["status"] == "REJECTED"
    assert (await c.post(f"/api/v1/admin/payments/withdrawals/{w2['id']}/reject", headers=h, json={"reason": "again"})).status_code == 409
    w = await wallet(env)
    assert (w.balance, w.pending_withdrawal) == (balance + 60_000, 0)
    assert [t.type for t in await ledger(env)].count("WITHDRAWAL_RELEASE") == 1

    integrity = (await c.get("/api/v1/admin/payments/integrity", headers=env["sa"])).json()
    assert integrity["ok"], integrity


async def test_withdrawal_guards(env):
    await make_account(env)
    await fund(env, amount=200_000)
    ben = await ready_to_withdraw(env)
    assert (await withdraw(env, ben, 50_000, pin="9999")).status_code == 403  # wrong PIN
    assert (await withdraw(env, ben, 999_999_00)).status_code == 400  # over max
    assert (await withdraw(env, ben, 190_000)).status_code == 201
    assert (await withdraw(env, ben, 50_000)).status_code == 400  # only 10,000 paise left
    assert (await wallet(env)).balance >= 0
    # Payout account still in cooling period
    r = await env["client"].post("/api/v1/payments/beneficiaries", headers=env["p1"],
                                 json={"method": "UPI", "holder_name": "Player One", "vpa": "player@oksbi", "pin": "2580"})
    assert (await withdraw(env, r.json(), 20_000)).status_code == 403
    # Someone else's payout account
    assert (await withdraw(env, ben, 20_000, uid="p2")).status_code in (400, 403, 404)


async def test_turnover_and_deposit_rules(env):
    await make_account(env)
    c = env["client"]
    await c.post("/api/v1/payments/pin", headers=env["p2"], json={"pin": "2580", "password": "Player@123"})
    elig = (await c.get("/api/v1/payments/withdrawals/eligibility", headers=env["p2"])).json()
    assert not elig["can_withdraw"] and "Make a successful deposit first" in elig["blockers"]
    await fund(env, "p2", 100_000)
    elig = (await c.get("/api/v1/payments/withdrawals/eligibility", headers=env["p2"])).json()
    assert any("turnover" in b for b in elig["blockers"])


async def test_user_cancel_releases_funds(env):
    await make_account(env)
    await fund(env, amount=300_000)
    ben = await ready_to_withdraw(env)
    balance = (await wallet(env)).balance
    wd = (await withdraw(env, ben, 100_000)).json()
    r = await env["client"].post(f"/api/v1/payments/withdrawals/{wd['id']}/cancel", headers=env["p1"])
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    w = await wallet(env)
    assert (w.balance, w.pending_withdrawal) == (balance, 0)


async def test_high_value_needs_maker_checker(env):
    await make_account(env)
    await fund(env, amount=1_000_000)
    ben = await ready_to_withdraw(env)
    async with env["db"]() as s:
        await platform_settings.update(s, {"withdrawal_high_value_paise": 200_000}, None)
        await s.commit()
    wd = (await withdraw(env, ben, 300_000)).json()
    c = env["client"]
    sa = await step(env, "sa", SA_SECRET)
    base = f"/api/v1/admin/payments/withdrawals/{wd['id']}"
    assert (await c.post(f"{base}/complete", headers=sa, json={"payout_reference": "RTGS00000001"})).status_code == 409
    assert (await c.post(f"{base}/initiate", headers=sa, json={})).status_code == 200  # super admin as maker
    assert (await c.post(f"{base}/complete", headers=sa, json={"payout_reference": "RTGS00000001"})).status_code == 403
    sa2 = await step(env, "sa2", SA_SECRET)
    r = await c.post(f"{base}/complete", headers=sa2, json={"payout_reference": "RTGS00000001"})
    assert r.status_code == 200 and r.json()["status"] == "COMPLETED"


async def test_stale_version_is_a_conflict(env):
    await make_account(env)
    await fund(env, amount=300_000)
    ben = await ready_to_withdraw(env)
    wd = (await withdraw(env, ben, 50_000)).json()
    detail = (await env["client"].get(f"/api/v1/admin/payments/withdrawals/{wd['id']}", headers=env["sa"])).json()
    r = await env["client"].post(f"/api/v1/admin/payments/withdrawals/{wd['id']}/complete", headers=await step(env, "sa", SA_SECRET),
                                 json={"payout_reference": "UPI000111222", "expected_version": detail["version"] + 1})
    assert r.status_code == 409


async def test_payout_details_super_admin_only_and_audited(env):
    await make_account(env)
    await fund(env, amount=300_000)
    ben = await ready_to_withdraw(env)
    wd = (await withdraw(env, ben, 50_000)).json()
    listed = (await env["client"].get("/api/v1/admin/payments/withdrawals", headers=env["a1"])).json()["items"]
    assert "123456789012" not in json.dumps(listed)  # masked for admins
    path = f"/api/v1/admin/payments/withdrawals/{wd['id']}/payout-details"
    assert (await env["client"].post(path, headers=await step(env, "a1", A1_SECRET))).status_code == 403
    full = (await env["client"].post(path, headers=await step(env, "sa", SA_SECRET))).json()
    assert full["account_number"] == "123456789012" and full["ifsc"] == "HDFC0001234"
    logs = (await env["client"].get("/api/v1/admin/audit-logs", headers=env["sa"], params={"action": "PAYOUT_DETAILS_VIEWED"})).json()
    assert "PAYOUT_DETAILS_VIEWED" in json.dumps(logs)


async def test_lookup_finds_by_utr_and_reference(env):
    await make_account(env)
    dep = await fund(env, amount=100_000)
    r = (await env["client"].get("/api/v1/admin/payments/lookup", headers=env["sa"], params={"q": dep["reference"]})).json()
    assert r["deposits"][0]["status"] == "SUCCESS"
    utr = r["deposits"][0]["utr"]
    r = (await env["client"].get("/api/v1/admin/payments/lookup", headers=env["sup"], params={"q": utr})).json()
    assert r["bank_credits"][0]["status"] == "MATCHED"


async def test_every_status_change_has_history(env):
    await make_account(env)
    dep = await fund(env, amount=100_000)
    detail = (await env["client"].get(f"/api/v1/admin/payments/deposits/{dep['id']}", headers=env["sa"])).json()
    assert [h["to"] for h in detail["history"]] == ["PENDING", "CREDITED"]
    assert detail["history"][1]["actor_type"] == "PROVIDER"
