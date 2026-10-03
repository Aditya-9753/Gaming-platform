"""Tests for Admin APIs: RBAC, audit logging for every write, dashboard, users, games, live rounds, roles, support, reports, and admin 2FA."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
import pyotp
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.constants import PermissionCode, UserRole
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.models.audit_log import AuditLog
from app.models.cricket import CricketMatchRecord
from app.models.game import Game, GameEntry, GameRound, GameSetting
from app.models.role import Permission, Role, RolePermission
from app.models.support import SupportTicket
from app.models.user import User
from app.models.wallet import Wallet
from app.services.auth_service import AuthService
from app.services.two_factor_service import two_factor_service

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def admin_env():
    """Setup in-memory SQLite database and test seed data."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Create roles
        role_user = Role(id=1, name="USER", description="Player")
        role_admin = Role(id=2, name="ADMIN", description="Administrator")
        role_super = Role(id=3, name="SUPERADMIN", description="Super Admin")
        session.add_all([role_user, role_admin, role_super])

        # Create all permissions
        perm_codes = [code.value for code in PermissionCode]
        perm_objs = [
            Permission(id=idx + 1, code=code, name=code, description=code)
            for idx, code in enumerate(perm_codes)
        ]
        session.add_all(perm_objs)
        await session.flush()

        # Admin gets all permissions
        for p in perm_objs:
            session.add(RolePermission(role_id=2, permission_id=p.id))
            session.add(RolePermission(role_id=3, permission_id=p.id))

        # Create normal player
        player = User(
            id="target_player_id",
            username="target_player",
            email="player@test.com",
            password_hash=hash_password("Password123!"),
            role_id=1,
            is_active=True,
        )
        session.add(player)

        # Create admin user
        totp_secret = two_factor_service.generate_secret()
        admin = User(
            id="admin_user_id",
            username="admin_user",
            email="admin@test.com",
            password_hash=hash_password("AdminPass123!"),
            role_id=2,
            is_active=True,
            totp_secret=totp_secret,
            totp_enabled=True,
        )
        session.add(admin)

        # Create super admin user
        super_admin = User(
            id="super_admin_id",
            username="super_user",
            email="super@test.com",
            password_hash=hash_password("SuperPass123!"),
            role_id=3,
            is_active=True,
            totp_secret=totp_secret,
            totp_enabled=True,
        )
        session.add(super_admin)

        # Create wallets
        w1 = Wallet(id="wallet_p1", user_id="target_player_id", balance=50000, locked_balance=0)
        session.add(w1)

        # Create game and setting
        game = Game(id="aviator", name="Aviator", type="CRASH", description="Crash", is_active=True)
        setting = GameSetting(game_id="aviator", min_bet=100, max_bet=50000, house_edge_percent=300)
        session.add_all([game, setting])

        # Create round and entry
        r = GameRound(
            id="live_round_1",
            game_id="aviator",
            round_no=1,
            status="BETTING",
            server_seed_hash="hash1",
            started_at=datetime.now(timezone.utc),
        )
        entry = GameEntry(
            id="entry_p1",
            round_id="live_round_1",
            user_id="target_player_id",
            bet_amount=200,
            payout_amount=0,
            status="PLACED",
            idempotency_key="entry_idem_1",
        )
        session.add_all([r, entry])

        # Create a support ticket
        ticket = SupportTicket(
            id="ticket_1",
            user_id="target_player_id",
            subject="Need help",
            status="OPEN",
            priority="NORMAL",
        )
        session.add(ticket)

        await session.commit()

    app = create_app()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        admin_token = create_access_token({"sub": "admin_user_id", "role": "ADMIN", "username": "admin_user"})
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        super_token = create_access_token({"sub": "super_admin_id", "role": "SUPERADMIN", "username": "super_user"})
        super_headers = {"Authorization": f"Bearer {super_token}"}

        player_token = create_access_token({"sub": "target_player_id", "role": "USER", "username": "target_player"})
        player_headers = {"Authorization": f"Bearer {player_token}"}

        yield {
            "client": client,
            "admin_headers": admin_headers,
            "super_headers": super_headers,
            "player_headers": player_headers,
            "session_factory": session_factory,
            "admin_id": "admin_user_id",
            "totp_secret": totp_secret,
        }

    await engine.dispose()


@pytest.mark.asyncio
async def test_rbac_permission_denied_cases(admin_env):
    """Test that unauthorized regular users get 403 Forbidden on admin endpoints."""
    client = admin_env["client"]
    player_headers = admin_env["player_headers"]

    # Regular player tries to access dashboard stats
    res = await client.get("/api/v1/admin/dashboard/stats", headers=player_headers)
    assert res.status_code == 403

    # Regular player tries to access users list
    res = await client.get("/api/v1/admin/users", headers=player_headers)
    assert res.status_code == 403

    # Regular player tries to update game settings
    res = await client.patch("/api/v1/admin/games/aviator/settings", headers=player_headers, json={"min_bet": 200})
    assert res.status_code == 403

    # Regular player tries to view audit logs
    res = await client.get("/api/v1/admin/audit-logs", headers=player_headers)
    assert res.status_code == 403

    # Administrator role and permission management is super-admin-only.
    res = await client.get("/api/v1/admin/roles", headers=admin_env["admin_headers"])
    assert res.status_code == 403

    async with admin_env["session_factory"]() as session:
        admin = await session.get(User, admin_env["admin_id"])
        admin.totp_enabled = False
        await session.commit()

    res = await client.get(
        "/api/v1/admin/dashboard/stats",
        headers=admin_env["admin_headers"],
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_admin_dashboard_stats(admin_env):
    """Test GET /admin/dashboard/stats returns aggregate metrics and chart series."""
    client = admin_env["client"]
    admin_headers = admin_env["admin_headers"]

    res = await client.get("/api/v1/admin/dashboard/stats", headers=admin_headers)
    assert res.status_code == 200
    stats = res.json()
    assert stats["users"] >= 2
    assert stats["live_games"] >= 1
    assert "rounds_played" in stats
    assert "chart_series" in stats
    assert len(stats["chart_series"]) == 7


@pytest.mark.asyncio
async def test_superadmin_can_create_admin_credentials_with_audit(admin_env):
    client = admin_env["client"]
    response = await client.post(
        "/api/v1/admin/admins",
        headers=admin_env["super_headers"],
        json={
            "username": "new_operator",
            "email": "operator@test.com",
            "password": "OperatorPass123!",
            "role": "ADMIN",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["username"] == "new_operator"
    assert body["email"] == "operator@test.com"
    assert body["role"] == "ADMIN"
    assert body["totp_enabled"] is False
    assert "password" not in body

    async with admin_env["session_factory"]() as session:
        created = await session.get(User, body["id"])
        assert created is not None
        from app.core.security import verify_password
        assert verify_password("OperatorPass123!", created.password_hash)
        wallet = (
            await session.execute(select(Wallet).where(Wallet.user_id == body["id"]))
        ).scalar_one()
        assert wallet.balance == 0
        audit = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "CREATE_ADMIN_USER",
                    AuditLog.target_id == body["id"],
                )
            )
        ).scalar_one()
        assert audit.actor_id == "super_admin_id"
        assert audit.details["role"] == "ADMIN"
        assert "password" not in audit.details

    denied = await client.post(
        "/api/v1/admin/admins",
        headers=admin_env["admin_headers"],
        json={
            "username": "not_super",
            "email": "not-super@test.com",
            "password": "OperatorPass123!",
            "role": "ADMIN",
        },
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_admin_users_operations_and_audit(admin_env):
    """Test user search, details, status block, wallet view, and balance adjustment with audit logging."""
    client = admin_env["client"]
    admin_headers = admin_env["admin_headers"]
    session_factory = admin_env["session_factory"]

    # 1. Search users
    res = await client.get("/api/v1/admin/users?q=target_player", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["total"] == 1

    # 2. Get user details
    res = await client.get("/api/v1/admin/users/target_player_id", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["username"] == "target_player"

    # 3. Block user with reason -> triggers audit log
    res = await client.patch(
        "/api/v1/admin/users/target_player_id/status",
        headers=admin_headers,
        json={"is_active": False, "reason": "Suspicious activity detected"},
    )
    assert res.status_code == 200
    assert res.json()["is_active"] is False

    # 4. View user wallet
    res = await client.get("/api/v1/admin/users/target_player_id/wallet", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["balance"] == 50000

    # 5. View user history & transactions
    res = await client.get("/api/v1/admin/users/target_player_id/history", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["total"] >= 1

    # 6. Manual wallet adjustment -> triggers audit log
    res = await client.post(
        "/api/v1/admin/users/target_player_id/adjust-balance",
        headers={**admin_headers, "Idempotency-Key": "admin-adjust-once"},
        json={"amount": 1000, "reason": "Goodwill courtesy credit"},
    )
    assert res.status_code == 200
    tx_id = res.json()["transaction_id"]
    replay = await client.post(
        "/api/v1/admin/users/target_player_id/adjust-balance",
        headers={**admin_headers, "Idempotency-Key": "admin-adjust-once"},
        json={"amount": 1000, "reason": "Goodwill courtesy credit"},
    )
    assert replay.status_code == 200
    assert replay.json()["transaction_id"] == tx_id
    conflict = await client.post(
        "/api/v1/admin/users/target_player_id/adjust-balance",
        headers={**admin_headers, "Idempotency-Key": "admin-adjust-once"},
        json={"amount": 2000, "reason": "Different adjustment"},
    )
    assert conflict.status_code == 409

    # 7. Verify audit logs created for status change and wallet adjust
    async with session_factory() as session:
        from sqlalchemy import select
        res = await session.execute(select(AuditLog).where(AuditLog.target_id == "target_player_id"))
        logs = res.scalars().all()
        actions = [l.action for l in logs]
        assert "SET_USER_STATUS" in actions
        assert "ADJUST_USER_BALANCE" in actions


@pytest.mark.asyncio
async def test_admin_games_management_and_audit(admin_env):
    """Test game enable/disable and game settings update with before/after audit log."""
    client = admin_env["client"]
    admin_headers = admin_env["admin_headers"]
    session_factory = admin_env["session_factory"]

    # 1. List games
    res = await client.get("/api/v1/admin/games", headers=admin_headers)
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 2. View settings
    res = await client.get("/api/v1/admin/games/aviator/settings", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["min_bet"] == 100

    # 3. Update settings with before/after audit log
    update_payload = {
        "min_bet": 200,
        "max_bet": 60000,
        "house_edge_percent": 350,
        "config": {"tick_rate_ms": 60},
    }
    res = await client.patch("/api/v1/admin/games/aviator/settings", headers=admin_headers, json=update_payload)
    assert res.status_code == 200
    assert res.json()["min_bet"] == 200

    # 4. Disable game -> triggers audit log
    res = await client.patch("/api/v1/admin/games/aviator/status", headers=admin_headers, json={"is_active": False})
    assert res.status_code == 200
    assert res.json()["is_active"] is False

    # 5. Verify audit logs
    async with session_factory() as session:
        from sqlalchemy import select
        res = await session.execute(select(AuditLog).where(AuditLog.target_id == "aviator"))
        logs = res.scalars().all()
        actions = [l.action for l in logs]
        assert "UPDATE_GAME_SETTINGS" in actions
        assert "SET_GAME_STATUS" in actions
        # Check before and after state captured in details
        settings_log = next(l for l in logs if l.action == "UPDATE_GAME_SETTINGS")
        assert "before" in settings_log.details
        assert "after" in settings_log.details
        assert settings_log.details["before"]["min_bet"] == 100
        assert settings_log.details["after"]["min_bet"] == 200

        # Game-specific timing and payout fields are validated before mutation.
        res = await client.patch(
            "/api/v1/admin/games/aviator/settings",
            headers=admin_headers,
            json={"config": {"growth_rate": -1}},
        )
        assert res.status_code == 400


@pytest.mark.asyncio
async def test_admin_live_rounds_and_history(admin_env):
    """Test live active rounds listing, round details, and historical rounds."""
    client = admin_env["client"]
    admin_headers = admin_env["admin_headers"]

    # 1. Live games
    res = await client.get("/api/v1/admin/games/live", headers=admin_headers)
    assert res.status_code == 200
    live = res.json()
    assert len(live) >= 1
    assert live[0]["round_id"] == "live_round_1"

    # 2. Round details
    res = await client.get("/api/v1/admin/rounds/live_round_1", headers=admin_headers)
    assert res.status_code == 200
    details = res.json()
    assert details["round_id"] == "live_round_1"
    assert len(details["entries"]) == 1

    # 3. Historical rounds
    res = await client.get("/api/v1/admin/rounds?game_id=aviator", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["total"] >= 1
    row = next(r for r in res.json()["items"] if r["round_id"] == "live_round_1")
    # running round: stake is counted, outcome and raw result stay hidden
    assert row["bets"] == 1 and row["wagered"] > 0
    assert row["outcome"] is None and row["result"] is None and row["server_seed"] is None


@pytest.mark.asyncio
async def test_admin_live_reports(admin_env):
    client = admin_env["client"]
    res = await client.get("/api/v1/admin/reports/live?days=7", headers=admin_env["admin_headers"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["daily"]) == 7
    assert len(body["last_hour"]) == 60
    assert {"wagered", "paid", "house_net", "bets", "players", "hold_pct"} <= set(body["today"])
    assert isinstance(body["games"], list)


@pytest.mark.asyncio
async def test_roles_and_admin_management_superadmin_only(admin_env):
    """Test superadmin role management, permission listing, and admin user assignment."""
    client = admin_env["client"]
    super_headers = admin_env["super_headers"]

    # 1. List roles
    res = await client.get("/api/v1/admin/roles", headers=super_headers)
    assert res.status_code == 200
    assert len(res.json()) >= 3

    # 2. List permissions
    res = await client.get("/api/v1/admin/permissions", headers=super_headers)
    assert res.status_code == 200
    assert len(res.json()) >= 5

    # 3. Create role -> triggers audit log
    res = await client.post(
        "/api/v1/admin/roles",
        headers=super_headers,
        json={"name": "VIP_SUPPORT", "description": "VIP Support team", "permission_codes": ["ticket:manage"]},
    )
    assert res.status_code == 200
    role_id = res.json()["id"]

    # 4. Update role permissions -> triggers audit log
    res = await client.put(
        f"/api/v1/admin/roles/{role_id}/permissions",
        headers=super_headers,
        json={"permission_codes": ["ticket:manage", "user:read"]},
    )
    assert res.status_code == 200

    # 5. List admin users
    res = await client.get("/api/v1/admin/admins", headers=super_headers)
    assert res.status_code == 200
    assert len(res.json()) >= 2


@pytest.mark.asyncio
async def test_admin_support_and_replies(admin_env):
    """Test support ticket listing, internal note reply, assign, and status update with audit log."""
    client = admin_env["client"]
    admin_headers = admin_env["admin_headers"]

    # 1. List tickets
    res = await client.get("/api/v1/admin/support/tickets", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["total"] >= 1

    # 2. Get ticket details with internal staff messages
    res = await client.get("/api/v1/admin/support/tickets/ticket_1", headers=admin_headers)
    assert res.status_code == 200

    # 3. Reply to ticket with internal staff note -> triggers audit log
    res = await client.post(
        "/api/v1/admin/support/tickets/ticket_1/reply",
        headers=admin_headers,
        json={"message": "Internal note: player reported payout issue", "is_internal": True},
    )
    assert res.status_code == 200
    assert res.json()["is_internal"] is True

    # 4. Assign ticket -> triggers audit log
    res = await client.patch(
        "/api/v1/admin/support/tickets/ticket_1/assign",
        headers=admin_headers,
        json={"assigned_to_id": "admin_user_id"},
    )
    assert res.status_code == 200

    # 5. Update ticket status -> triggers audit log
    res = await client.patch(
        "/api/v1/admin/support/tickets/ticket_1/status",
        headers=admin_headers,
        json={"status": "IN_PROGRESS"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_admin_notifications_broadcast_and_reports(admin_env):
    """Test notification broadcast and CSV reports export."""
    client = admin_env["client"]
    admin_headers = admin_env["admin_headers"]

    # 1. Broadcast notification -> triggers audit log
    res = await client.post(
        "/api/v1/admin/notifications/broadcast",
        headers=admin_headers,
        json={"title": "Maintenance Alert", "message": "Scheduled maintenance in 1 hour.", "notification_type": "SYSTEM"},
    )
    assert res.status_code == 200
    assert res.json()["recipients_count"] >= 1

    # 2. CSV report export (users)
    res = await client.get("/api/v1/admin/reports/export/users", headers=admin_headers)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "username,email" in res.text

    # 3. Read-only Audit logs listing
    res = await client.get("/api/v1/admin/audit-logs?page=1&page_size=20", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_cricket_settlement_override_is_permissioned_and_audited(admin_env):
    client = admin_env["client"]
    async with admin_env["session_factory"]() as session:
        session.add(
            CricketMatchRecord(
                id="override-match",
                home_team="Falcons",
                away_team="Tigers",
                status="SCHEDULED",
                abandoned=False,
                metadata_json={},
            )
        )
        await session.commit()

    path = "/api/v1/admin/cricket/matches/override-match/settle"
    body = {"abandoned": True, "reason": "Official match was abandoned"}
    denied = await client.post(
        path,
        headers=admin_env["player_headers"],
        json=body,
    )
    assert denied.status_code == 403

    response = await client.post(
        path,
        headers={
            **admin_env["admin_headers"],
            "Idempotency-Key": "cricket-override-1",
        },
        json=body,
    )
    assert response.status_code == 200
    async with admin_env["session_factory"]() as session:
        log = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "CRICKET_SETTLEMENT_OVERRIDE",
                    AuditLog.target_id == "override-match",
                )
            )
        ).scalar_one()
        assert log.details["reason"] == body["reason"]
        assert log.details["before"]["status"] == "SCHEDULED"
        assert log.details["after"]["status"] == "ABANDONED"


@pytest.mark.asyncio
async def test_admin_2fa_enforcement(admin_env):
    """Test that admin login requires 2FA enrollment and valid TOTP code."""
    session_factory = admin_env["session_factory"]
    totp_secret = admin_env["totp_secret"]

    async with session_factory() as session:
        auth_svc = AuthService(session)

        # Admin with 2FA enabled must provide its current authenticator code.
        from app.core.exceptions import UnauthorizedException
        with pytest.raises(UnauthorizedException) as excinfo:
            await auth_svc.login("admin@test.com", "AdminPass123!", totp_code=None)
        assert "Authenticator code required" in str(excinfo.value)

        # 2. Admin login with invalid TOTP code raises UnauthorizedException
        with pytest.raises(UnauthorizedException) as excinfo:
            await auth_svc.login("admin@test.com", "AdminPass123!", totp_code="000000")
        assert "Invalid authenticator code" in str(excinfo.value)

        # 3. Admin login with valid TOTP code succeeds
        valid_totp = pyotp.TOTP(totp_secret).now()
        user, access, refresh = await auth_svc.login("admin@test.com", "AdminPass123!", totp_code=valid_totp)
        assert user.id == "admin_user_id"
        assert access is not None


@pytest.mark.asyncio
async def test_audit_logs_append_only(admin_env):
    """Test that audit log records cannot be updated or deleted in code (append-only enforcement)."""
    session_factory = admin_env["session_factory"]

    async with session_factory() as session:
        # Create an audit log
        log = AuditLog(
            action="TEST_ACTION",
            target_type="TEST",
            actor_id="admin_user_id",
            details={"key": "val"},
        )
        session.add(log)
        await session.commit()
        log_id = log.id

    # Attempting to modify must raise PermissionError
    async with session_factory() as session:
        log_to_update = await session.get(AuditLog, log_id)
        log_to_update.action = "TAMPERED_ACTION"
        with pytest.raises(PermissionError) as excinfo:
            await session.commit()
        assert "append-only and cannot be modified" in str(excinfo.value)

    # Attempting to delete must raise PermissionError
    async with session_factory() as session:
        log_to_delete = await session.get(AuditLog, log_id)
        await session.delete(log_to_delete)
        with pytest.raises(PermissionError) as excinfo:
            await session.commit()
        assert "append-only and cannot be deleted" in str(excinfo.value)


# =========================================================================
# Super admin operations
# =========================================================================


@pytest.mark.asyncio
async def test_superadmin_demo_credit_block_and_remove_admin(admin_env):
    client, sup, adm = admin_env["client"], admin_env["super_headers"], admin_env["admin_headers"]

    # Only the super admin may grant demo credits (admin gets 403)
    denied = await client.post("/api/v1/admin/admins/admin_user_id/demo-credit", headers=adm, json={"amount_paise": 1000})
    assert denied.status_code == 403
    res = await client.post("/api/v1/admin/admins/admin_user_id/demo-credit", headers=sup, json={"amount_paise": 250_000, "note": "QA"})
    assert res.status_code == 200, res.text
    assert res.json()["balance_after"] == 250_000  # wallet created on demand

    # Players are not staff accounts
    assert (await client.post("/api/v1/admin/admins/target_player_id/demo-credit", headers=sup, json={"amount_paise": 100})).status_code == 403

    # Block -> the admin is locked out; unblock restores access
    assert (await client.patch("/api/v1/admin/admins/admin_user_id/status", headers=sup, json={"is_active": False, "reason": "audit"})).status_code == 200
    assert (await client.get("/api/v1/admin/users", headers=adm)).status_code == 403
    assert (await client.patch("/api/v1/admin/admins/admin_user_id/status", headers=sup, json={"is_active": True})).status_code == 200
    assert (await client.get("/api/v1/admin/users", headers=adm)).status_code == 200

    # Activity + searchable audit trail
    activity = await client.get("/api/v1/admin/admins/admin_user_id/activity", headers=sup)
    assert activity.status_code == 200
    found = await client.get("/api/v1/admin/audit-logs", headers=sup, params={"q": "DEMO_CREDIT"})
    assert found.json()["total"] >= 1

    # Remove = demoted to player + disabled (history kept)
    assert (await client.delete("/api/v1/admin/admins/admin_user_id", headers=sup)).status_code == 200
    async with admin_env["session_factory"]() as session:
        removed = await session.get(User, "admin_user_id")
        assert removed.is_active is False and removed.role_id == 1


@pytest.mark.asyncio
async def test_maintenance_mode_blocks_player_bets(admin_env):
    client, sup = admin_env["client"], admin_env["super_headers"]
    res = await client.put("/api/v1/admin/system-settings", headers=sup, json={"values": {"maintenance_mode": True, "platform_name": "GameZone Pro"}})
    assert res.status_code == 200 and res.json()["values"]["maintenance_mode"] is True
    public = await client.get("/api/v1/system/config")
    assert public.json()["platform_name"] == "GameZone Pro"

    bet = await client.post(
        "/api/v1/games/wingo/action",
        headers={**admin_env["player_headers"], "Idempotency-Key": "maint-1"},
        json={"game_id": "wingo_30s", "round_id": "x", "amount": 100, "bet_type": "COLOR", "value": "GREEN"},
    )
    assert bet.status_code == 503

    bad = await client.put("/api/v1/admin/system-settings", headers=sup, json={"values": {"unknown_key": 1}})
    assert bad.status_code == 400
    await client.put("/api/v1/admin/system-settings", headers=sup, json={"values": {"maintenance_mode": False}})


@pytest.mark.asyncio
async def test_void_round_refunds_open_stakes(admin_env):
    client, sup = admin_env["client"], admin_env["super_headers"]
    async with admin_env["session_factory"]() as session:
        wallet = await session.get(Wallet, "wallet_p1")
        wallet.locked_balance = 200  # the PLACED 200 stake from the fixture
        await session.commit()

    assert (await client.post("/api/v1/admin/rounds/live_round_1/void", headers=admin_env["admin_headers"], json={"reason": "incident"})).status_code == 403
    res = await client.post("/api/v1/admin/rounds/live_round_1/void", headers=sup, json={"reason": "server incident"})
    assert res.status_code == 200, res.text
    assert res.json() == {"round_id": "live_round_1", "refunded_entries": 1, "refunded_paise": 200}
    async with admin_env["session_factory"]() as session:
        entry = await session.get(GameEntry, "entry_p1")
        wallet = await session.get(Wallet, "wallet_p1")
        assert entry.status == "REFUNDED" and wallet.locked_balance == 0


@pytest.mark.asyncio
async def test_finance_overview_is_superadmin_only(admin_env):
    client = admin_env["client"]
    assert (await client.get("/api/v1/admin/finance/overview", headers=admin_env["admin_headers"])).status_code == 403
    res = await client.get("/api/v1/admin/finance/overview", headers=admin_env["super_headers"], params={"days": 7})
    assert res.status_code == 200 and "totals" in res.json()


@pytest.mark.asyncio
async def test_add_new_admin_superadmin_only_with_custom_role(admin_env):
    client, sup, adm = admin_env["client"], admin_env["super_headers"], admin_env["admin_headers"]
    body = {"full_name": "Riya Sharma", "username": "riya_ops", "email": "Riya@Example.com", "password": "Str0ng!Passw0rd", "role": "ADMIN"}

    # A normal admin can neither list staff nor create one (API-enforced, not just hidden)
    assert (await client.post("/api/v1/admin/admins", headers=adm, json=body)).status_code == 403
    assert (await client.get("/api/v1/admin/admins", headers=adm)).status_code == 403

    created = await client.post("/api/v1/admin/admins", headers=sup, json=body)
    assert created.status_code == 201, created.text
    assert created.json()["full_name"] == "Riya Sharma" and created.json()["email"] == "riya@example.com"

    # Uniqueness is case-insensitive for login ID and email
    dup_id = await client.post("/api/v1/admin/admins", headers=sup, json={**body, "username": "RIYA_OPS", "email": "other@example.com"})
    dup_mail = await client.post("/api/v1/admin/admins", headers=sup, json={**body, "username": "riya2", "email": "RIYA@example.com"})
    assert dup_id.status_code == 409 and dup_mail.status_code == 409
    # Weak passwords and the super admin role are rejected
    assert (await client.post("/api/v1/admin/admins", headers=sup, json={**body, "username": "weak1", "email": "w@x.io", "password": "short"})).status_code == 422
    assert (await client.post("/api/v1/admin/admins", headers=sup, json={**body, "username": "boss2", "email": "b@x.io", "role": "SUPERADMIN"})).status_code == 400

    # Custom roles from the Roles system are allowed
    role = await client.post("/api/v1/admin/roles", headers=sup, json={"name": "GAME_OPERATOR", "description": "Runs games", "permission_codes": ["game:manage"]})
    assert role.status_code == 200
    custom = await client.post("/api/v1/admin/admins", headers=sup, json={**body, "username": "gameop", "email": "op@x.io", "role": "GAME_OPERATOR"})
    assert custom.status_code == 201 and custom.json()["role"] == "GAME_OPERATOR"

    # Password stored hashed; creation audited with actor + IP
    async with admin_env["session_factory"]() as session:
        user = (await session.execute(select(User).where(User.username == "riya_ops"))).scalar_one()
        assert user.password_hash != body["password"] and user.password_hash.startswith("$argon2")
        log = (await session.execute(select(AuditLog).where(AuditLog.action == "CREATE_ADMIN_USER", AuditLog.target_id == user.id))).scalar_one()
        assert log.actor_id == "super_admin_id" and log.ip_address
    staff = (await client.get("/api/v1/admin/admins", headers=sup)).json()
    assert {"riya_ops", "gameop"} <= {s["username"] for s in staff}


@pytest.mark.asyncio
async def test_live_dashboard_counts_real_players_only(admin_env):
    client, sup = admin_env["client"], admin_env["super_headers"]
    async with admin_env["session_factory"]() as session:
        session.add(User(id="bot1", username="Rahul_King", email=None, password_hash="x", role_id=1, is_active=True))
        session.add(GameEntry(id="bot_bet", round_id="live_round_1", user_id="bot1", bet_amount=5000, payout_amount=0, status="PLACED", idempotency_key="bot_bet"))
        await session.commit()

    real = (await client.get("/api/v1/admin/dashboard/live", headers=sup)).json()
    assert real["include_bots"] is False
    assert real["kpis"]["players_total"] == 1          # target_player only; staff and bots excluded
    assert real["kpis"]["bets_today"] == 1 and real["kpis"]["wagered_today"] == 200
    assert [b["username"] for b in real["recent_bets"]] == ["target_player"]
    assert len(real["hourly"]) == 24
    aviator = next(g for g in real["games"] if g["game_id"] == "aviator")
    assert aviator["bets"] == 1 and aviator["round_no"] == 1

    with_bots = (await client.get("/api/v1/admin/dashboard/live", headers=sup, params={"include_bots": True})).json()
    assert with_bots["kpis"]["players_total"] == 2 and with_bots["kpis"]["wagered_today"] == 5200

    assert (await client.get("/api/v1/admin/dashboard/live", headers=admin_env["player_headers"])).status_code == 403


@pytest.mark.asyncio
async def test_live_dashboard_drilldowns_and_game_detail(admin_env):
    client, sup = admin_env["client"], admin_env["super_headers"]
    async with admin_env["session_factory"]() as session:
        round_obj = await session.get(GameRound, "live_round_1")
        round_obj.server_seed = "secret-seed-value"
        if await session.get(Game, "cricket") is None:
            session.add(Game(id="cricket", name="Cricket", type="cricket", is_active=True))
        await session.commit()

    game = (await client.get("/api/v1/admin/dashboard/live/games/aviator", headers=sup)).json()
    assert game["current"]["round_no"] == 1
    assert [b["username"] for b in game["live_bets"]] == ["target_player"]
    assert "secret-seed-value" not in str(game)

    players = (await client.get("/api/v1/admin/dashboard/live/drilldown/players", headers=sup)).json()
    assert players["shape"] == "players" and [r["username"] for r in players["rows"]] == ["target_player"]
    bets = (await client.get("/api/v1/admin/dashboard/live/drilldown/bets_today", headers=sup)).json()
    assert bets["shape"] == "bets" and len(bets["rows"]) == 1
    hour = (await client.get("/api/v1/admin/dashboard/live/drilldown/hour", headers=sup, params={"hour": 0})).json()
    assert len(hour["rows"]) == 1
    assert (await client.get("/api/v1/admin/dashboard/live/drilldown/nope", headers=sup)).status_code == 404

    bet = (await client.get(f"/api/v1/admin/dashboard/live/bets/{bets['rows'][0]['id']}", headers=sup)).json()
    assert bet["round"]["server_seed"] is None          # round still running: seed stays secret
    assert (await client.get("/api/v1/admin/dashboard/live/games/cricket", headers=sup)).status_code == 200
    assert (await client.get("/api/v1/admin/dashboard/live/games/aviator", headers=admin_env["player_headers"])).status_code == 403


TEST_AUDIT_KEY = "11" * 32


@pytest.mark.asyncio
async def test_integrity_seals_detect_direct_database_edits(admin_env, monkeypatch):
    from sqlalchemy import update

    from app.core.config import get_settings
    from app.models.wallet import WalletTransaction

    settings = get_settings()

    client, sup = admin_env["client"], admin_env["super_headers"]
    status = (await client.get("/api/v1/admin/integrity/status", headers=sup)).json()
    assert status["configured"] is False
    assert (await client.post("/api/v1/admin/integrity/verify", headers=sup, json={"kind": "ledger"})).status_code == 400

    monkeypatch.setattr(settings, "AUDIT_ENCRYPTION_KEY", TEST_AUDIT_KEY)
    async with admin_env["session_factory"]() as session:
        wallet = (await session.execute(select(Wallet))).scalars().first()
        tx = WalletTransaction(wallet_id=wallet.id, idempotency_key="seal-test", type="BET", amount=500,
                               balance_before=1000, balance_after=500, status="COMPLETED", reference="seal")
        session.add(tx)
        session.add(AuditLog(action="SEAL_TEST", target_type="SYSTEM"))
        await session.commit()
        assert tx.integrity_seal and tx.integrity_seal.startswith("v1.")
        tx_id = tx.id

    ok = (await client.post("/api/v1/admin/integrity/verify", headers=sup, json={"kind": "ledger"})).json()
    assert ok["ok"] == 1 and ok["tampered"] == 0
    audit = (await client.post("/api/v1/admin/integrity/verify", headers=sup, json={"kind": "audit"})).json()
    assert audit["ok"] >= 1 and audit["tampered"] == 0

    # Someone edits the ledger straight in the database
    async with admin_env["session_factory"]() as session:
        await session.execute(update(WalletTransaction).where(WalletTransaction.id == tx_id).values(amount=50))
        await session.commit()
    bad = (await client.post("/api/v1/admin/integrity/verify", headers=sup, json={"kind": "ledger"})).json()
    assert bad["tampered"] == 1
    assert bad["tampered_rows"][0]["changes"]["amount"] == {"sealed": 500, "now": 50}

    sealed = (await client.post("/api/v1/admin/integrity/seal-existing", headers=sup, json={"kind": "audit"})).json()
    assert sealed["sealed"] >= 0
    after = (await client.get("/api/v1/admin/integrity/status", headers=sup)).json()
    assert after["configured"] is True and after["tables"]["audit"]["unsealed"] == 0
    assert (await client.get("/api/v1/admin/integrity/status", headers=admin_env["player_headers"])).status_code == 403


@pytest.mark.asyncio
async def test_hold_analyzer_and_simulation(admin_env):
    client, sup = admin_env["client"], admin_env["super_headers"]
    async with admin_env["session_factory"]() as session:
        session.add(Game(id="wingo_1m", name="WinGo 1 Min", type="wingo", is_active=True))
        session.add(GameRound(id="wg_round", game_id="wingo_1m", round_no=1, status="COMPLETED", server_seed_hash="h" * 64))
        for i, (status, payout) in enumerate([("WON", 900), ("LOST", 0), ("LOST", 0)]):
            session.add(GameEntry(id=f"wg_{i}", round_id="wg_round", user_id="target_player_id", bet_amount=100,
                                  payout_amount=payout, status=status, idempotency_key=f"wg_{i}",
                                  selection={"type": "NUMBER", "value": str(i)}))
        await session.commit()

    report = (await client.get("/api/v1/admin/hold/analysis", headers=sup)).json()
    wingo = next(g for g in report["games"] if g["game_id"] == "wingo_1m")
    assert wingo["wagered"] == 300 and wingo["paid"] == 900
    assert wingo["actual_hold_pct"] == -200.0 and wingo["expected_hold_pct"] == 10.0

    sim = (await client.post("/api/v1/admin/hold/simulate", headers=sup,
                             json={"game": "wingo", "rounds": 5000, "payouts": {"NUMBER": 8.5}, "use_bet_mix": False})).json()
    assert sim["rounds"] == 5000 and sum(sim["number_counts"]) == 5000 and len(sim["server_seed"]) == 64
    assert abs(sim["simulated_hold_pct"] - sim["expected_hold_pct"]) < 5
    avi = (await client.post("/api/v1/admin/hold/simulate", headers=sup, json={"game": "aviator", "rounds": 2000, "cashout_at": 2})).json()
    assert 0 < avi["win_rate_pct"] < 100
    bad = await client.post("/api/v1/admin/hold/simulate", headers=sup, json={"game": "mines", "mine_count": 20, "reveal": 10})
    assert bad.status_code == 400
    assert (await client.get("/api/v1/admin/hold/analysis", headers=admin_env["player_headers"])).status_code == 403


@pytest.mark.asyncio
async def test_client_seed_rotation_applies_to_new_rounds(admin_env):
    from app.services.fairness_service import FairnessService

    client, sup = admin_env["client"], admin_env["super_headers"]
    first = (await client.post("/api/v1/admin/fairness/client-seed/rotate", headers=sup, json={})).json()
    seed1 = first["active"]["seed"]
    assert len(seed1) == 32 and first["history"] == []

    async with admin_env["session_factory"]() as session:
        new_round = await FairnessService(session).create_round_seed("aviator", 999)
        assert new_round.client_seed == seed1

    second = (await client.post("/api/v1/admin/fairness/client-seed/rotate", headers=sup, json={"seed": "diwali-2026-seed"})).json()
    assert second["active"]["seed"] == "diwali-2026-seed" and second["history"][0]["seed"] == seed1
    assert (await client.post("/api/v1/admin/fairness/client-seed/rotate", headers=sup, json={"seed": "bad seed!"})).status_code == 400
    assert (await client.post("/api/v1/admin/fairness/client-seed/rotate", headers=admin_env["player_headers"], json={})).status_code == 403


@pytest.mark.asyncio
async def test_backtest_replays_rounds_and_flags_bad_settlements(admin_env):
    from app.games.wingo.rules import compute_outcome, payouts_from_config
    from app.services.backtest import chi_square
    from app.utils.rng import hash_server_seed

    client, sup = admin_env["client"], admin_env["super_headers"]
    seed = "a" * 64
    drawn = compute_outcome(seed, "bt-client", 7)
    other = (drawn.number + 1) % 10
    async with admin_env["session_factory"]() as session:
        session.add(Game(id="wingo_30s", name="WinGo 30s", type="wingo", is_active=True))
        session.add(GameRound(id="bt_round", game_id="wingo_30s", round_no=7, status="HISTORY", server_seed=seed,
                              server_seed_hash=hash_server_seed(seed), client_seed="bt-client",
                              result={"number": drawn.number, "colours": list(drawn.colours), "size": drawn.size,
                                      "payouts_x100": payouts_from_config(None)}))
        # Correct win, correct loss, and one loss that should have been a win
        session.add(GameEntry(id="bt_win", round_id="bt_round", user_id="target_player_id", bet_amount=100, payout_amount=900,
                              status="WON", idempotency_key="bt_win", selection={"type": "NUMBER", "value": str(drawn.number)}))
        session.add(GameEntry(id="bt_loss", round_id="bt_round", user_id="target_player_id", bet_amount=100, payout_amount=0,
                              status="LOST", idempotency_key="bt_loss", selection={"type": "NUMBER", "value": str(other)}))
        session.add(GameEntry(id="bt_wrong", round_id="bt_round", user_id="target_player_id", bet_amount=100, payout_amount=0,
                              status="LOST", idempotency_key="bt_wrong", selection={"type": "NUMBER", "value": str(drawn.number)}))
        await session.commit()

    report = (await client.post("/api/v1/admin/backtest/run", headers=sup, json={"days": 30})).json()
    wg = report["replay"]["games"]["wingo_30s"]
    assert wg["rounds"] == 1 and wg["hash_ok"] == 1 and wg["outcome_ok"] == 1
    assert wg["bets"] == 3 and wg["settled_ok"] == 2
    assert wg["issues"][0]["entry_id"] == "bt_wrong" and "rules say WON" in wg["issues"][0]["problem"]
    checks = {c["name"]: c["status"] for c in report["verdict"]["checks"]}
    assert checks["Seed commitments"] == "pass" and checks["Bet settlement"] == "fail"
    assert report["verdict"]["status"] == "fail"
    assert sum(report["statistics"]["wingo"]["number_counts"]) == report["statistics"]["wingo"]["rounds"]

    stored = (await client.get("/api/v1/admin/backtest/latest", headers=sup)).json()
    assert stored["report"]["generated_at"] == report["generated_at"] and stored["history"][0]["status"] == "fail"
    assert (await client.post("/api/v1/admin/backtest/run", headers=admin_env["player_headers"], json={})).status_code == 403

    # chi-square helper against textbook values
    assert chi_square([10] * 10, [10.0] * 10)["p_value"] == 1.0
