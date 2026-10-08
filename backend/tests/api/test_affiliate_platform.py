"""Partner / affiliate platform: the whole chain from link to payout.

partner -> tracking link -> click -> S2S registration / deposit / revenue ->
commission -> ledger -> settlement -> withdrawal, plus RBAC, staff 2FA, maker-checker,
impersonation, subpartners, the internal operator bridge and the KPI formulas.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.affiliate import analytics, ledger, operator_bridge, stats
from app.affiliate import settings as aff_settings
from app.affiliate.constants import DealType
from app.core import rate_limit
from app.core.config import get_settings
from app.core.constants import ROLE_PERMISSIONS, PermissionCode, UserRole
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import create_app
from app.models.affiliate import (
    AffCommission,
    AffCommissionPlan,
    AffFxRate,
    AffIngestEvent,
    AffPartner,
    AffRegistration,
    AffSettlementPeriod,
    AffTrackingClick,
    AffWallet,
    AffWithdrawalMethod,
)
from app.models.role import Permission, Role, RolePermission
from app.models.user import User

INGEST_SECRET = "ingest-test-secret"
SA, A1, F1, F2, SUP = (pyotp.random_base32() for _ in range(5))


@pytest.fixture
async def env(monkeypatch):
    import fakeredis

    from app.core import redis as redis_module

    monkeypatch.setattr(redis_module, "redis_client", fakeredis.aioredis.FakeRedis(decode_responses=True))
    rate_limit._memory_store.clear()
    rate_limit._lockout_store.clear()
    aff_settings.reset_cache()
    analytics._memory_dirty.clear()
    monkeypatch.setattr(get_settings(), "AFFILIATE_INGEST_SECRET", INGEST_SECRET)
    monkeypatch.setattr(get_settings(), "AFFILIATE_PUBLIC_BASE_URL", "https://rudra.test")
    monkeypatch.setattr(get_settings(), "AFFILIATE_FX_AUTO_FETCH", False)  # no network in tests
    monkeypatch.setattr(get_settings(), "AFFILIATE_BREACH_CHECK", False)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        roles = [UserRole.USER, UserRole.ADMIN, UserRole.SUPERADMIN, UserRole.SUPPORT, UserRole.FINANCE_ADMIN, UserRole.PARTNER]
        role_ids = {r: i + 1 for i, r in enumerate(roles)}
        s.add_all([Role(id=i, name=r.value) for r, i in role_ids.items()])
        perms = {c: Permission(id=n + 1, code=c.value, name=c.value) for n, c in enumerate(PermissionCode)}
        s.add_all(perms.values())
        await s.flush()
        for role, rid in role_ids.items():
            s.add_all([RolePermission(role_id=rid, permission_id=perms[c].id) for c in ROLE_PERMISSIONS[role]])

        def staff(uid, role, secret):
            return User(id=uid, username=uid, email=f"{uid}@staff.io", password_hash="x", role_id=role_ids[role],
                        is_active=True, is_verified=True, totp_enabled=True, totp_secret=secret, two_factor_method="totp")

        s.add_all([staff("sa", UserRole.SUPERADMIN, SA), staff("a1", UserRole.ADMIN, A1), staff("f1", UserRole.FINANCE_ADMIN, F1),
                   staff("f2", UserRole.FINANCE_ADMIN, F2), staff("sup", UserRole.SUPPORT, SUP)])
        s.add(AffFxRate(rate_date=date(2026, 1, 1), currency="INR", rate_to_usd=Decimal("0.012")))
        s.add(AffCommissionPlan(name="Revshare 50%", deal_type=DealType.REVSHARE, default_revshare_rate=Decimal("0.5"),
                                default_cpa_amount=Decimal("0"), min_ftd_amount=Decimal("0"), hold_days=14, carryover=True))
        await s.commit()

    app = create_app()

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override

    def auth(uid, role):
        return {"Authorization": f"Bearer {create_access_token({'sub': uid, 'role': role})}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield {"client": client, "db": factory, "sa": auth("sa", "SUPERADMIN"), "a1": auth("a1", "ADMIN"),
               "f1": auth("f1", "FINANCE_ADMIN"), "f2": auth("f2", "FINANCE_ADMIN"), "sup": auth("sup", "SUPPORT"), "auth": auth}
    await engine.dispose()


# ------------------------------------------------------------------ helpers


def signed(body: dict, ts=None, secret=INGEST_SECRET):
    raw = json.dumps(body).encode()
    ts = str(int(ts if ts is not None else time.time()))
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    return raw, {"X-Timestamp": ts, "X-Signature": sig, "Content-Type": "application/json"}


async def ingest(env, kind, body, **kw):
    raw, headers = signed(body, **kw)
    return await env["client"].post(f"/api/v1/ingest/{kind}", content=raw, headers=headers)


async def create_partner(env, email="partner@example.com", deal=None, parent=None):
    body = {"email": email, "password": "Strong#Aff2026xyz", "profile": {"first_name": "Ravi"}}
    if deal:
        body["deal"] = deal
    if parent:
        body["parent_partner_id"] = parent
    who = "sa" if deal else "a1"
    r = await env["client"].post("/api/v1/aff/admin/partners", headers=env[who], json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    async with env["db"]() as db:
        partner = await db.get(AffPartner, data["partner"]["id"])
        data["user_id"] = partner.user_id
        data["headers"] = env["auth"](partner.user_id, "PARTNER")
    return data


async def click(env, code, ip="203.0.113.7", **subs):
    params = "&".join(f"{k}={v}" for k, v in subs.items())
    r = await env["client"].get(f"/r/{code}" + (f"?{params}" if params else ""),
                                headers={"user-agent": "Mozilla/5.0 (Linux; Android 14) Chrome/120 Mobile",
                                         "x-forwarded-for": ip, "cf-ipcountry": "IN"})
    assert r.status_code == 302, r.text
    return r


def click_id_from(response) -> str:
    from urllib.parse import parse_qs, urlsplit

    return parse_qs(urlsplit(response.headers["location"]).query)["click_id"][0]


async def wallet(env, partner_id):
    async with env["db"]() as db:
        w = (await db.execute(select(AffWallet).where(AffWallet.partner_id == partner_id))).scalar_one()
        return w.available_balance, w.pending_balance, w.reserved_balance


async def rebuild(env):
    async with env["db"]() as db:
        await analytics.rebuild(db, datetime(2020, 1, 1, tzinfo=timezone.utc), datetime.now(timezone.utc) + timedelta(days=2))
    from app.core import redis as redis_module

    await redis_module.redis_client.flushdb()


async def close_current_period(env):
    """Close the open period now (only the super admin may close a period before it ends)."""
    async with env["db"]() as db:
        period = (await db.execute(select(AffSettlementPeriod).where(AffSettlementPeriod.status == "OPEN")
                                   .order_by(AffSettlementPeriod.start_date))).scalars().first()
        period_id = period.id
    return await env["client"].post(f"/api/v1/aff/admin/periods/{period_id}/close", headers=env["sa"])


# ------------------------------------------------------------------ tests


async def test_partner_creation_default_link_and_click(env):
    data = await create_partner(env)
    link = data["default_link"]
    code = data["partner"]["partner_code"]
    assert len(code) == 8 and not set(code) & set("01OI")
    assert link["link_code"] == code and link["is_default"]
    assert link["urls"]["query"] == f"https://rudra.test/?ref={code}"
    assert link["urls"]["redirect"] == f"https://rudra.test/r/{code}"
    assert await wallet(env, data["partner"]["id"]) == (0, 0, 0)

    r = await click(env, code, sub1="tg_post")
    assert r.headers["location"].startswith("https://rudra.test/register?")
    assert "aff_click=" in r.headers.get("set-cookie", "")
    cid = click_id_from(r)
    async with env["db"]() as db:
        row = (await db.execute(select(AffTrackingClick).where(AffTrackingClick.click_id == cid))).scalar_one()
        assert row.sub1 == "tg_post" and row.country == "IN" and row.device_type == "mobile" and not row.is_bot
        assert row.ip_hash and "203.0.113.7" not in row.ip_hash  # IP stored only as a salted hash

    # query-style link on the API root and the JSON variant used by the main site
    r = await env["client"].get(f"/?ref={code}", headers={"user-agent": "Mozilla/5.0 Chrome/120"})
    assert r.status_code == 302
    r = await env["client"].post("/api/v1/aff/track/click", json={"ref": code, "sub2": "x"}, headers={"user-agent": "Mozilla/5.0 Chrome/120"})
    assert r.json()["tracked"] and len(r.json()["click_id"]) == 26
    # bots are logged but flagged, unknown codes go to the main site untracked
    r = await env["client"].get(f"/r/{code}", headers={"user-agent": "curl/8.0"})
    async with env["db"]() as db:
        bot = (await db.execute(select(AffTrackingClick).where(AffTrackingClick.click_id == click_id_from(r)))).scalar_one()
        assert bot.is_bot and not bot.is_unique
    r = await env["client"].get("/r/NOPE2345")
    assert r.headers["location"] == "https://rudra.test" and "click_id" not in r.headers["location"]


async def test_full_chain_revshare_kpis_settlement_and_withdrawal(env):
    data = await create_partner(env)
    pid, code, ph = data["partner"]["id"], data["partner"]["partner_code"], data["headers"]

    cid = click_id_from(await click(env, code))
    r = await ingest(env, "registration", {"external_customer_id": "cust-1", "click_id": cid, "country": "IN",
                                           "registered_at": datetime.now(timezone.utc).isoformat()})
    assert r.status_code == 201 and r.json()["status"] == "PROCESSED", r.text
    dup = await ingest(env, "registration", {"external_customer_id": "cust-1", "click_id": cid, "country": "IN"})
    assert dup.status_code == 200 and dup.json()["duplicate"] and dup.json()["id"] == r.json()["id"]

    today = date.today()
    r = await ingest(env, "deposit", {"external_customer_id": "cust-1", "external_transaction_id": "tx-1", "amount": "100",
                                      "currency": "USD", "status": "COMPLETED", "completed_at": datetime.now(timezone.utc).isoformat()})
    assert r.status_code == 201 and r.json()["status"] == "PROCESSED", r.text
    r = await ingest(env, "revenue", {"rows": [{"external_customer_id": "cust-1", "date": today.isoformat(),
                                                "bets": "500", "wins": "300", "bonuses": "0"}]})
    assert r.json()["status"] == "PROCESSED", r.text
    available, pending, reserved = await wallet(env, pid)
    assert pending == Decimal("100") and available == 0  # 50% of NGR 200

    # revenue for the same day changes: only the difference is posted
    await ingest(env, "revenue", {"rows": [{"external_customer_id": "cust-1", "date": today.isoformat(), "ngr": "260"}]})
    assert (await wallet(env, pid))[1] == Decimal("130")

    await rebuild(env)
    r = await env["client"].get("/api/v1/aff/dashboard/summary?period=all", headers=ph)
    assert r.status_code == 200, r.text
    k = r.json()
    assert k["transitions"] == 1 and k["registrations"] == 1 and k["first_deposits"] == 1 and k["deposit_count"] == 1
    assert k["amount_deposit"] == "100.00" and k["income"] == "130.00"
    assert k["ratio_registrations"] == "1.00" and k["ratio_deposits"] == "100.00" and k["cost_transition"] == "130.00"
    assert k["avg_player_income"] == "260.00"  # (130 / 0.5) / 1
    series = (await env["client"].get("/api/v1/aff/dashboard/timeseries?period=7d", headers=ph)).json()["series"]
    assert len(series) == 7 and series[-1]["registrations"] == 1 and series[-1]["income"] == "130.00"

    # finance closes the period: pending -> available
    r = await close_current_period(env)
    assert r.status_code == 200, r.text
    assert await wallet(env, pid) == (Decimal("130"), Decimal("0"), Decimal("0"))
    stmt = (await env["client"].get("/api/v1/aff/wallet/statements", headers=ph)).json()["items"][0]
    assert stmt["revshare_total"] == "130.00" and stmt["closing_balance"] == "130.00"

    # partners withdraw without 2FA (the 24h payout-method cool-down still applies)
    w = (await env["client"].get("/api/v1/aff/wallet", headers=ph)).json()
    assert w["can_withdraw"] and w["withdraw_blocked_reason"] is None
    assert (await env["client"].post("/api/v1/aff/2fa/setup", headers=ph)).status_code == 404
    r = await env["client"].post("/api/v1/aff/withdrawal-methods", headers=ph,
                                 json={"type": "EWALLET_EMAIL", "account_identifier": "ravi.partner@gmail.com"})
    assert r.status_code == 201, r.text
    method = r.json()
    assert method["destination"] == "ra****@gmail.com"
    async with env["db"]() as db:
        raw = (await db.get(AffWithdrawalMethod, method["id"])).account_identifier_encrypted
        assert "ravi.partner" not in raw  # encrypted at rest

    async def withdraw(amount, key=None):
        return await env["client"].post("/api/v1/aff/withdrawals", headers={**ph, "Idempotency-Key": key or uuid.uuid4().hex},
                                        json={"amount": amount})

    r = await withdraw("50")
    assert r.status_code == 400 and "cool-down" in r.text
    async with env["db"]() as db:
        await db.execute(update(AffWithdrawalMethod).values(usable_after=datetime.now(timezone.utc) - timedelta(minutes=1)))
        await db.commit()
    assert (await withdraw("10")).status_code == 400  # below min payout (20)
    assert (await withdraw("500")).status_code == 400  # above available
    key = uuid.uuid4().hex
    r = await withdraw("100", key=key)
    assert r.status_code == 201, r.text
    wd = r.json()
    again = await withdraw("100", key=key)
    assert again.json()["id"] == wd["id"]  # idempotent
    assert (await withdraw("20")).status_code == 409  # one open request at a time
    assert await wallet(env, pid) == (Decimal("30"), Decimal("0"), Decimal("100"))

    base = f"/api/v1/aff/admin/withdrawals/{wd['id']}"
    assert (await env["client"].post(f"{base}/approve", headers=env["a1"], json={})).status_code == 403  # admin is not finance
    assert (await env["client"].post(f"{base}/approve", headers=env["f1"], json={})).status_code == 200
    assert (await env["client"].post(f"{base}/mark-paid", headers=env["f1"], json={})).status_code == 400  # needs a reference
    r = await env["client"].post(f"{base}/mark-paid", headers=env["f1"], json={"external_payment_reference": "SKRILL-991"})
    assert r.json()["status"] == "COMPLETED"
    assert await wallet(env, pid) == (Decimal("30"), Decimal("0"), Decimal("0"))
    detail = (await env["client"].get(f"/api/v1/aff/withdrawals/{wd['id']}", headers=ph)).json()
    assert [h["to"] for h in detail["history"]] == ["PENDING", "APPROVED", "COMPLETED"]

    async with env["db"]() as db:
        assert await ledger.reconcile(db) == []


async def test_negative_revshare_carryover_and_writeoff(env):
    data = await create_partner(env, deal={"deal_type": "REVSHARE", "revshare_rate": "0.5", "carryover": False})
    other = await create_partner(env, email="carry@example.com")
    for partner, cust in ((data, "neg-1"), (other, "neg-2")):
        cid = click_id_from(await click(env, partner["partner"]["partner_code"]))
        await ingest(env, "registration", {"external_customer_id": cust, "click_id": cid})
    await ingest(env, "revenue", {"rows": [
        {"external_customer_id": "neg-1", "date": date.today().isoformat(), "bets": "100", "wins": "537"},
        {"external_customer_id": "neg-2", "date": date.today().isoformat(), "bets": "100", "wins": "536.62"},
    ]})
    assert (await wallet(env, data["partner"]["id"]))[1] == Decimal("-218.5")
    assert (await close_current_period(env)).status_code == 200
    # carryover off: written off to zero; carryover on (default plan): stays negative like the reference account
    assert (await wallet(env, data["partner"]["id"]))[0] == 0
    assert (await wallet(env, other["partner"]["id"]))[0] == Decimal("-218.31")
    w = (await env["client"].get("/api/v1/aff/wallet", headers=other["headers"])).json()
    assert w["available"] == "-218.31" and not w["can_withdraw"] and "Negative balance" in w["withdraw_blocked_reason"]
    me = (await env["client"].get("/api/v1/aff/me", headers=other["headers"])).json()
    assert me["wallet"]["available"] == "-218.31" and me["deal"]["revshare_rate"] == "0.5000"


async def test_cpa_hold_and_chargeback_reversal(env):
    data = await create_partner(env, deal={"deal_type": "CPA", "cpa_amount": "40", "min_ftd_amount": "20",
                                           "cpa_geo_list": ["IN"], "hold_days": 14})
    pid, code = data["partner"]["id"], data["partner"]["partner_code"]
    for n, (amount, country) in enumerate((("10", "IN"), ("50", "IN"), ("50", "BR"))):
        cid = click_id_from(await click(env, code, ip=f"198.51.100.{n}"))
        await ingest(env, "registration", {"external_customer_id": f"c{n}", "click_id": cid, "country": country})
        await ingest(env, "deposit", {"external_customer_id": f"c{n}", "external_transaction_id": f"t{n}", "amount": amount,
                                      "currency": "USD", "status": "COMPLETED"})
    # only c1 qualifies (c0 below the minimum FTD, c2 outside the CPA GEO list)
    assert (await wallet(env, pid))[1] == Decimal("40")
    async with env["db"]() as db:
        held = (await db.execute(select(AffCommission).where(AffCommission.partner_id == pid))).scalars().all()
        assert len(held) == 1 and held[0].status.value == "HELD"
    assert (await close_current_period(env)).status_code == 200
    assert await wallet(env, pid) == (Decimal("0"), Decimal("40"), Decimal("0"))  # still on hold

    r = await ingest(env, "reversal", {"external_reversal_id": "cb-1", "external_transaction_id": "t1", "reason": "chargeback"})
    assert r.json()["status"] == "PROCESSED", r.text
    assert await wallet(env, pid) == (Decimal("0"), Decimal("0"), Decimal("0"))
    events = (await env["client"].get("/api/v1/aff/admin/risk-events", headers=env["a1"])).json()["items"]
    assert any(e["event_type"] == "CPA_REVERSED" for e in events)


async def test_held_cpa_settles_after_hold(env):
    data = await create_partner(env, deal={"deal_type": "HYBRID", "cpa_amount": "25", "revshare_rate": "0.25", "hold_days": 1})
    pid = data["partner"]["id"]
    cid = click_id_from(await click(env, data["partner"]["partner_code"]))
    await ingest(env, "registration", {"external_customer_id": "h1", "click_id": cid})
    await ingest(env, "deposit", {"external_customer_id": "h1", "external_transaction_id": "ht1", "amount": "30", "currency": "USD"})
    async with env["db"]() as db:
        await db.execute(update(AffCommission).values(hold_until=datetime.now(timezone.utc) - timedelta(hours=1)))
        await db.commit()
    await ingest(env, "revenue", {"rows": [{"external_customer_id": "h1", "date": date.today().isoformat(), "ngr": "100"}]})
    assert (await wallet(env, pid))[1] == Decimal("50")  # 25 CPA + 25% of 100
    assert (await close_current_period(env)).status_code == 200
    assert await wallet(env, pid) == (Decimal("50"), Decimal("0"), Decimal("0"))


async def test_ingest_security_and_fx(env):
    raw, headers = signed({"external_customer_id": "x"}, secret="wrong")
    assert (await env["client"].post("/api/v1/ingest/registration", content=raw, headers=headers)).status_code == 401
    assert (await ingest(env, "registration", {"external_customer_id": "x"}, ts=time.time() - 3600)).status_code == 401
    assert (await env["client"].post("/api/v1/ingest/registration", json={"external_customer_id": "x"})).status_code == 401

    data = await create_partner(env)
    cid = click_id_from(await click(env, data["partner"]["partner_code"]))
    await ingest(env, "registration", {"external_customer_id": "inr-1", "click_id": cid})
    r = await ingest(env, "deposit", {"external_customer_id": "inr-1", "external_transaction_id": "inr-tx", "amount": "1000",
                                      "currency": "INR"})
    assert r.json()["status"] == "PROCESSED"
    deposits = (await env["client"].get("/api/v1/aff/admin/deposits", headers=env["a1"])).json()["items"]
    assert deposits[0]["amount_usd"] == "12.00"  # stored INR rate 0.012 (latest on or before the day)
    # unknown currency: kept as FAILED, visible and retryable in the ingest monitor
    r = await ingest(env, "deposit", {"external_customer_id": "inr-1", "external_transaction_id": "jpy", "amount": "1", "currency": "JPY"})
    assert r.json()["status"] == "FAILED" and "FX" in r.json()["error"]
    event_id = r.json()["id"]
    failed = (await env["client"].get("/api/v1/aff/admin/ingest-events?status=FAILED", headers=env["a1"])).json()
    assert [e["id"] for e in failed["items"]] == [event_id]
    r = await env["client"].post("/api/v1/aff/admin/fx-rates", headers=env["f1"],
                                 json={"rate_date": date.today().isoformat(), "currency": "JPY", "rate_to_usd": "0.0068"})
    assert r.status_code == 201
    r = await env["client"].post(f"/api/v1/aff/admin/ingest-events/{event_id}/retry", headers=env["a1"])
    assert r.json()["status"] == "PROCESSED", r.text
    # a later duplicate delivery returns the same, now processed, event
    again = await ingest(env, "deposit", {"external_customer_id": "inr-1", "external_transaction_id": "jpy", "amount": "1", "currency": "JPY"})
    assert again.status_code == 200 and again.json()["id"] == event_id and again.json()["status"] == "PROCESSED"


async def test_rbac_maker_checker_and_impersonation(env):
    data = await create_partner(env)
    pid, ph = data["partner"]["id"], data["headers"]
    # support can look up but not change partners; partners cannot reach admin APIs
    assert (await env["client"].get("/api/v1/aff/admin/partners", headers=env["sup"])).status_code == 200
    assert (await env["client"].post(f"/api/v1/aff/admin/partners/{pid}/status", headers=env["sup"], json={"status": "SUSPENDED"})).status_code == 403
    assert (await env["client"].get("/api/v1/aff/admin/partners", headers=ph)).status_code == 403
    assert (await env["client"].post("/api/v1/aff/admin/tracking-domains", headers=env["a1"], json={"domain": "go.example.com"})).status_code == 403
    assert (await env["client"].post(f"/api/v1/aff/admin/partners/{pid}/deal", headers=env["a1"], json={"revshare_rate": "0.4"})).status_code == 403

    r = await env["client"].post("/api/v1/aff/admin/adjustments", headers=env["f1"],
                                 json={"partner_id": pid, "direction": "CREDIT", "amount": "25", "reason": "Missed CPA"})
    adj = r.json()
    r = await env["client"].post(f"/api/v1/aff/admin/adjustments/{adj['id']}/decide", headers=env["f1"], json={"approve": True})
    assert r.status_code == 403  # the maker cannot approve
    r = await env["client"].post(f"/api/v1/aff/admin/adjustments/{adj['id']}/decide", headers=env["f2"], json={"approve": True})
    assert r.json()["status"] == "APPROVED"
    assert (await wallet(env, pid))[0] == Decimal("25")

    token = (await env["client"].post(f"/api/v1/aff/admin/partners/{pid}/impersonate", headers=env["sup"])).json()["access_token"]
    view = {"Authorization": f"Bearer {token}"}
    me = (await env["client"].get("/api/v1/aff/me", headers=view)).json()
    assert me["impersonated_by"] == "sup"
    r = await env["client"].post("/api/v1/aff/sources", headers=view, json={"name": "Hack"})
    assert r.status_code == 403 and "read-only" in r.text

    # suspension blocks the portal; partners only ever see their own data
    other = await create_partner(env, email="other@example.com")
    r = await env["client"].patch(f"/api/v1/aff/tracking-links/{other['default_link']['id']}", headers=ph, json={"name": "mine"})
    assert r.status_code == 404
    await env["client"].post(f"/api/v1/aff/admin/partners/{pid}/status", headers=env["a1"], json={"status": "SUSPENDED", "reason": "test"})
    r = await env["client"].get("/api/v1/aff/dashboard/summary", headers=ph)
    assert r.status_code == 403 and r.json()["error"]["code"] == "PARTNER_SUSPENDED"
    audit = (await env["client"].get("/api/v1/aff/admin/audit-logs", headers=env["sa"])).json()["items"]
    assert {"AFF_PARTNER_CREATED", "AFF_ADJUSTMENT_APPROVED", "AFF_IMPERSONATION_STARTED", "AFF_PARTNER_STATUS"} <= {a["action"] for a in audit}


async def test_self_signup_subpartner_and_sub_commission(env):
    master = await create_partner(env, email="master@example.com")
    invite = (await env["client"].get("/api/v1/aff/me/invite-link", headers=master["headers"])).json()["url"]
    assert invite.endswith(f"inviter={master['partner']['partner_code']}")

    r = await env["client"].post("/api/v1/aff/auth/signup", json={"email": "sub@example.com", "password": "short", "confirm_adult": True})
    assert r.status_code == 422
    r = await env["client"].post("/api/v1/aff/auth/signup", json={
        "email": "sub@example.com", "password": "Sub#Partner2026!", "confirm_adult": True, "accept_terms": True,
        "inviter": master["partner"]["partner_code"], "profile": {"first_name": "Sub"}})
    assert r.status_code == 201 and r.json()["status"] == "PENDING", r.text
    async with env["db"]() as db:
        sub = (await db.execute(select(AffPartner).where(AffPartner.parent_partner_id == master["partner"]["id"]))).scalar_one()
        sub_headers = env["auth"](sub.user_id, "PARTNER")
    r = await env["client"].get("/api/v1/aff/dashboard/summary", headers=sub_headers)
    assert r.status_code == 403  # email not verified / pending approval
    async with env["db"]() as db:
        await db.execute(update(User).where(User.id == sub.user_id).values(is_verified=True))
        await db.commit()
    await env["client"].post(f"/api/v1/aff/admin/partners/{sub.id}/status", headers=env["a1"], json={"status": "ACTIVE"})
    assert (await env["client"].get("/api/v1/aff/dashboard/summary", headers=sub_headers)).status_code == 200
    assert (await env["client"].get("/api/v1/aff/me/invite-link", headers=sub_headers)).status_code == 400  # depth 1

    cid = click_id_from(await click(env, sub.partner_code))
    await ingest(env, "registration", {"external_customer_id": "sp-1", "click_id": cid})
    await ingest(env, "revenue", {"rows": [{"external_customer_id": "sp-1", "date": date.today().isoformat(), "ngr": "400"}]})
    assert (await close_current_period(env)).status_code == 200
    assert (await wallet(env, sub.id))[0] == Decimal("200")
    assert (await wallet(env, master["partner"]["id"]))[0] == Decimal("10")  # 5% of the subpartner's 200
    await rebuild(env)
    rows = (await env["client"].get("/api/v1/aff/statistics/subpartners", headers=master["headers"])).json()["items"]
    assert rows[0]["partner_code"] == sub.partner_code and rows[0]["your_commission"] == "10.00"
    assert "customer" not in json.dumps(rows)


async def test_rudra247_signup_reports_to_affiliate(env):
    data = await create_partner(env)
    cid = click_id_from(await click(env, data["partner"]["partner_code"]))
    r = await env["client"].post("/api/v1/auth/register", json={"username": "newplayer", "password": "Player123",
                                                                "age_confirmed": True, "click_id": cid})
    assert r.status_code == 201, r.text
    async with env["db"]() as db:
        event = (await db.execute(select(AffIngestEvent))).scalar_one()
        assert event.source == "INTERNAL" and event.status.value == "RECEIVED"
        await operator_bridge.process_outbox(db)
        reg = (await db.execute(select(AffRegistration))).scalar_one()
        assert reg.partner_id == data["partner"]["id"] and reg.click_id == cid


def test_kpi_formulas_match_reference_account():
    totals = {"clicks": 11339, "registrations": 1963, "first_deposits": 359, "deposit_count": 2001,
              "deposit_amount": Decimal("20589.04"), "income": Decimal("4322.8"), "ngr": Decimal("0"),
              "sub_commission": Decimal("0"), "unique_clicks": 0}
    k = stats.kpis(totals, DealType.REVSHARE, Decimal("0.5"))
    assert (k["ratio_registrations"], k["ratio_deposits"], k["cost_transition"], k["avg_player_income"]) == ("5.78", "10.49", "0.38", "24.08")
    assert k["income"] == "4322.80" and k["amount_deposit"] == "20589.04"
    empty = stats.kpis({**totals, "clicks": 0, "registrations": 0, "first_deposits": 0}, DealType.REVSHARE, Decimal("0.5"))
    assert empty["ratio_registrations"] is None and empty["cost_transition"] is None and empty["avg_player_income"] is None


async def test_tiered_deal_adjusts_at_close(env):
    data = await create_partner(env, deal={"deal_type": "TIERED", "tier_table": [
        {"min_ngr": "0", "rate": "0.25"}, {"min_ngr": "1000", "rate": "0.40"}]})
    pid = data["partner"]["id"]
    cid = click_id_from(await click(env, data["partner"]["partner_code"]))
    await ingest(env, "registration", {"external_customer_id": "t1", "click_id": cid})
    await ingest(env, "revenue", {"rows": [{"external_customer_id": "t1", "date": date.today().isoformat(), "ngr": "1500"}]})
    assert (await wallet(env, pid))[1] == Decimal("375")  # provisional 25%
    assert (await close_current_period(env)).status_code == 200
    assert (await wallet(env, pid))[0] == Decimal("600")  # tier 40% for period NGR 1500
    async with env["db"]() as db:
        assert await ledger.reconcile(db) == []


async def test_fx_sync_stores_inverted_reference_rates(env, monkeypatch):
    from app.affiliate import fx

    async def fake_fetch():
        return date(2026, 10, 8), {"INR": (Decimal(1) / Decimal("96.78")).quantize(Decimal("0.00000001"))}

    monkeypatch.setattr(fx, "fetch_latest", fake_fetch)
    r = await env["client"].post("/api/v1/aff/admin/fx-rates/sync", headers=env["f1"])
    assert r.status_code == 200 and r.json() == {"date": "2026-10-08", "currencies": 1}
    rates = (await env["client"].get("/api/v1/aff/admin/fx-rates", headers=env["f1"])).json()["items"]
    assert rates[0]["currency"] == "INR" and Decimal(rates[0]["rate_to_usd"]) == Decimal("0.01033271")


async def test_login_captcha_after_five_failures_then_lock(env, monkeypatch):
    from app.services import captcha_service

    monkeypatch.setattr(get_settings(), "TURNSTILE_SITE_KEY", "site-key")
    monkeypatch.setattr(get_settings(), "TURNSTILE_SECRET_KEY", "secret-key")
    good_tokens = {"ok-token"}

    async def fake_verify(token, ip):
        return token in good_tokens

    monkeypatch.setattr(captcha_service, "verify", fake_verify)
    await create_partner(env, email="cap@example.com")

    async def login(password, token=None):
        return await env["client"].post("/api/v1/auth/login", json={"username": "cap@example.com", "password": password, "captcha_token": token})

    for _ in range(4):
        assert (await login("wrong-password-1")).status_code == 401
    r = await login("wrong-password-1")  # 5th failure: captcha from now on
    assert r.status_code == 403 and r.json()["error"]["code"] == "CAPTCHA_REQUIRED" and r.json()["error"]["details"]["site_key"] == "site-key"
    assert (await login("Strong#Aff2026xyz")).json()["error"]["code"] == "CAPTCHA_REQUIRED"  # even the right password needs it
    assert (await login("Strong#Aff2026xyz", "bad-token")).json()["error"]["code"] == "CAPTCHA_REQUIRED"
    assert (await login("Strong#Aff2026xyz", "ok-token")).status_code == 200

    # with the captcha on, the lock comes after 10 failures instead of 5
    rate_limit._memory_store.clear()
    rate_limit._lockout_store.clear()
    from app.core import redis as redis_module

    await redis_module.redis_client.flushdb()
    for n in range(1, 11):
        await rate_limit.record_failed_login("x@example.com", "1.2.3.4", lock_after=captcha_service.LOCK_AFTER)
        assert (await rate_limit.is_locked_out("x@example.com", "1.2.3.4"))[0] is (n >= 10)
