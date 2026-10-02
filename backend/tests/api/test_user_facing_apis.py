"""Tests for user-facing APIs: games, users, notifications, support, responsible play, and leaderboard."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.constants import PermissionCode, UserRole
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.models.game import Game, GameEntry, GameRound, GameSetting
from app.models.notification import Notification
from app.models.role import Permission, Role, RolePermission
from app.models.user import User
from app.models.wallet import Wallet
from app.services.leaderboard_service import LeaderboardService
from app.services.notification_service import NotificationService
from app.services.responsible_play_service import ResponsiblePlayService
from app.services.wallet_service import WalletService
from app.games.cricket.providers.base import CricketMatch
from app.games.cricket.providers.mock import MockCricketDataProvider
from app.workers.tasks_leaderboard import run_leaderboard_refresh

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def test_env():
    """Setup in-memory SQLite database and test seed data."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Create roles
        role_user = Role(id=1, name="USER", description="Player")
        role_admin = Role(id=2, name="ADMIN", description="Administrator")
        session.add_all([role_user, role_admin])

        # Create permissions
        play_perm = Permission(id=1, code=PermissionCode.GAME_PLAY.value, name="Play", description="Play games")
        hist_perm = Permission(id=2, code=PermissionCode.HISTORY_READ.value, name="History", description="History")
        session.add_all([play_perm, hist_perm])
        await session.flush()

        session.add(RolePermission(role_id=1, permission_id=1))
        session.add(RolePermission(role_id=1, permission_id=2))

        # Create test users
        player = User(
            id="test_player_id",
            username="player_one",
            email="player1@test.com",
            password_hash=hash_password("Password123!"),
            role_id=1,
            is_active=True,
        )
        session.add(player)

        # Create player wallet
        wallet = Wallet(
            id="wallet_player_1",
            user_id="test_player_id",
            balance=100000,  # 1000 Credits
            locked_balance=0,
            currency="VIRTUAL",
        )
        session.add(wallet)

        # Create game
        game = Game(
            id="aviator",
            name="Aviator",
            type="CRASH",
            description="Crash game",
            is_active=True,
        )
        session.add(game)
        setting = GameSetting(
            game_id="aviator",
            min_bet=100,
            max_bet=50000,
            house_edge_percent=300,
        )
        session.add(setting)

        # Create rounds
        r1 = GameRound(
            id="round_c1",
            game_id="aviator",
            round_no=1,
            status="COMPLETED",
            server_seed_hash="hash1",
            server_seed="seed1",
            client_seed="cseed1",
            result={"crash_point": 2.50},
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
        )
        r2 = GameRound(
            id="round_b1",
            game_id="aviator",
            round_no=2,
            status="BETTING",
            server_seed_hash="hash2",
            started_at=datetime.now(timezone.utc),
        )
        session.add_all([r1, r2])

        # Create game entries
        entry1 = GameEntry(
            id="entry_1",
            round_id="round_c1",
            user_id="test_player_id",
            bet_amount=500,
            payout_amount=1250,
            status="WON",
            multiplier=250,
            idempotency_key="idem_entry_1",
        )
        session.add(entry1)

        await session.commit()

    app = create_app()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = create_access_token({"sub": "test_player_id", "role": "USER", "username": "player_one"})
        headers = {"Authorization": f"Bearer {token}"}
        yield {
            "client": client,
            "headers": headers,
            "session_factory": session_factory,
            "user_id": "test_player_id",
        }

    await engine.dispose()


@pytest.mark.asyncio
async def test_games_catalog_and_history(test_env):
    """Test GET /games, GET /games/{id}, GET /games/{id}/rounds, GET /games/{id}/history."""
    client = test_env["client"]
    headers = test_env["headers"]

    # 1. GET /games
    res = await client.get("/api/v1/games", headers=headers)
    assert res.status_code == 200
    games = res.json()
    assert len(games) >= 1
    assert games[0]["id"] == "aviator"

    # 2. GET /games/{id}
    res = await client.get("/api/v1/games/aviator", headers=headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Aviator"

    # 3. GET /games/{id}/rounds (paginated, with status filter)
    res = await client.get("/api/v1/games/aviator/rounds?status=COMPLETED", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] == 1
    assert data["items"][0]["status"] == "COMPLETED"

    # 4. GET /games/{id}/history (paginated)
    res = await client.get("/api/v1/games/aviator/history?page=1&page_size=10", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["server_seed"] == "seed1"

    res = await client.get(
        "/api/v1/games/aviator/history"
        "?status=COMPLETED&from_date=2020-01-01T00:00:00Z"
        "&to_date=2030-01-01T00:00:00Z",
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["total"] == 1

    res = await client.get(
        "/api/v1/games/aviator/history"
        "?from_date=2030-01-01T00:00:00Z&to_date=2020-01-01T00:00:00Z",
        headers=headers,
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_user_me_profile_and_history(test_env):
    """Test GET /users/me, PUT /users/me, and GET /users/me/history."""
    client = test_env["client"]
    headers = test_env["headers"]

    # 1. GET /users/me
    res = await client.get("/api/v1/users/me", headers=headers)
    assert res.status_code == 200
    me = res.json()
    assert me["username"] == "player_one"
    assert me["email"] == "player1@test.com"
    assert me["is_self_excluded"] is False

    # 2. PUT /users/me
    res = await client.put(
        "/api/v1/users/me",
        headers=headers,
        json={"username": "player_renamed"},
    )
    assert res.status_code == 200
    assert res.json()["username"] == "player_renamed"

    # Verify updated profile
    res = await client.get("/api/v1/users/me", headers=headers)
    assert res.json()["username"] == "player_renamed"

    # 3. GET /users/me/history
    res = await client.get("/api/v1/users/me/history?page=1&page_size=10", headers=headers)
    assert res.status_code == 200
    history = res.json()
    assert "items" in history
    assert history["total"] >= 1
    assert history["items"][0]["bet_amount"] == 500


@pytest.mark.asyncio
async def test_notifications_endpoints_and_service(test_env):
    """Test notification service, paginated list, unread count, and mark as read."""
    client = test_env["client"]
    headers = test_env["headers"]
    session_factory = test_env["session_factory"]
    user_id = test_env["user_id"]

    # Create notifications via service
    async with session_factory() as session:
        notif_svc = NotificationService(session)
        await notif_svc.send_result_notification(user_id, "Aviator", 1, True, 1250)
        await notif_svc.send_system_notification(user_id, "Platform Update", "System update completed")
        await notif_svc.send_account_notification(user_id, "Security Notice", "Login from new device")
        await session.commit()

    # 1. GET /notifications/unread-count
    res = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert res.status_code == 200
    assert res.json()["unread_count"] == 3

    # 2. GET /notifications (paginated)
    res = await client.get("/api/v1/notifications?page=1&page_size=10", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    notif_id = data["items"][0]["id"]

    # 3. POST /notifications/{id}/read
    res = await client.post(f"/api/v1/notifications/{notif_id}/read", headers=headers)
    assert res.status_code == 200
    assert res.json()["success"] is True

    # 4. POST /notifications/read-all
    res = await client.post("/api/v1/notifications/read-all", headers=headers)
    assert res.status_code == 200
    assert res.json()["marked_read"] == 2

    # Verify unread count is 0
    res = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert res.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_support_tickets_and_threads(test_env):
    """Test ticket creation, threaded messaging, and user replies."""
    client = test_env["client"]
    headers = test_env["headers"]

    # 1. POST /support/tickets
    create_payload = {
        "subject": "Missing payout question",
        "message": "Hello, I have a question regarding round 1 payout.",
        "priority": "NORMAL",
    }
    res = await client.post("/api/v1/support/tickets", headers=headers, json=create_payload)
    assert res.status_code == 200
    ticket = res.json()
    ticket_id = ticket["id"]
    assert ticket["status"] == "OPEN"

    # 2. GET /support/tickets (list)
    res = await client.get("/api/v1/support/tickets", headers=headers)
    assert res.status_code == 200
    assert res.json()["total"] >= 1

    # 3. POST /support/tickets/{id}/reply
    res = await client.post(
        f"/api/v1/support/tickets/{ticket_id}/reply",
        headers=headers,
        json={"message": "Here is additional info about my round."},
    )
    assert res.status_code == 200
    assert res.json()["message"] == "Here is additional info about my round."

    # 4. GET /support/tickets/{id}
    res = await client.get(f"/api/v1/support/tickets/{ticket_id}", headers=headers)
    assert res.status_code == 200
    details = res.json()
    assert details["id"] == ticket_id
    assert len(details["messages"]) == 2  # initial message + user reply


@pytest.mark.asyncio
async def test_responsible_play_and_bet_blocking(test_env):
    """Test daily limits, session reminders, self-exclusion (24h/7d/permanent) and betting blocking in wallet_service."""
    client = test_env["client"]
    headers = test_env["headers"]
    session_factory = test_env["session_factory"]
    user_id = test_env["user_id"]

    # 1. Configure session reminders
    res = await client.post(
        "/api/v1/responsible-play/session-reminders",
        headers=headers,
        json={"interval_minutes": 30, "enabled": True},
    )
    assert res.status_code == 200
    assert res.json()["session_reminders"]["interval_minutes"] == 30

    # 2. Configure daily limits (1000 paise daily bet limit)
    res = await client.post(
        "/api/v1/responsible-play/limits",
        headers=headers,
        json={"daily_bet_limit_paise": 1000, "daily_loss_limit_paise": 500},
    )
    assert res.status_code == 200
    assert res.json()["limits"]["daily_bet_limit_paise"] == 1000

    # 3. Test that wallet_service.place_bet blocks when exceeding daily bet limit
    async with session_factory() as session:
        wallet_svc = WalletService(session)
        # Attempt bet of 1500 paise (exceeds 1000 limit)
        from app.core.exceptions import ForbiddenException
        with pytest.raises(ForbiddenException) as excinfo:
            await wallet_svc.place_bet(
                user_id=user_id,
                amount_paise=1500,
                idempotency_key="over_limit_bet",
            )
        assert "Daily wager limit" in str(excinfo.value)

    # 4. Apply self-exclusion (24h)
    res = await client.post(
        "/api/v1/responsible-play/self-exclusion",
        headers=headers,
        json={"period": "24h", "reason": "Need a break"},
    )
    assert res.status_code == 200
    assert res.json()["is_active"] is True

    # 5. Verify wallet_service.place_bet is strictly blocked during self-exclusion
    async with session_factory() as session:
        wallet_svc = WalletService(session)
        with pytest.raises(ForbiddenException) as excinfo:
            await wallet_svc.place_bet(
                user_id=user_id,
                amount_paise=100,
                idempotency_key="excluded_bet_attempt",
            )
        assert "Active self-exclusion" in str(excinfo.value)

    # 6. Verify responsible play status endpoint
    res = await client.get("/api/v1/responsible-play/status", headers=headers)
    assert res.status_code == 200
    assert res.json()["is_self_excluded"] is True


@pytest.mark.asyncio
async def test_zero_daily_limit_blocks_all_wagers(test_env):
    """A configured zero limit blocks wagering rather than disabling the limit."""
    session_factory = test_env["session_factory"]
    user_id = test_env["user_id"]
    async with session_factory() as session:
        await ResponsiblePlayService(session).update_user_limits(
            user_id=user_id,
            daily_bet_limit_paise=0,
        )
        await session.commit()
    async with session_factory() as session:
        from app.core.exceptions import ForbiddenException

        with pytest.raises(ForbiddenException, match="Daily wager limit"):
            await WalletService(session).place_bet(
                user_id=user_id,
                amount_paise=100,
                idempotency_key="zero-limit-bet",
            )


@pytest.mark.asyncio
async def test_cricket_market_router_with_mock_provider(test_env, monkeypatch):
    client = test_env["client"]
    provider = MockCricketDataProvider(
        [
            CricketMatch(
                "router-match",
                "Falcons",
                "Tigers",
                "SCHEDULED",
                metadata={"competition": "Test Cup"},
            )
        ]
    )
    async with test_env["session_factory"]() as session:
        session.add(Game(id="cricket", name="Cricket", type="SPORTS", is_active=True))
        session.add(
            GameSetting(
                game_id="cricket",
                min_bet=100,
                max_bet=50_000,
                config={"home_odds_bp": 200, "away_odds_bp": 250},
            )
        )
        await session.commit()
    monkeypatch.setattr(
        "app.api.v1.games.routes.get_cricket_provider", lambda: provider
    )
    monkeypatch.setattr(
        "app.api.v1.games.routes.get_redis_client", lambda: None
    )

    matches = await client.get("/api/v1/games/cricket/matches")
    assert matches.status_code == 200
    assert matches.json()["items"][0]["match_id"] == "router-match"
    details = await client.get("/api/v1/games/cricket/matches/router-match")
    assert details.json()["home_team"] == "Falcons"
    score = await client.get(
        "/api/v1/games/cricket/matches/router-match/live-score"
    )
    assert score.json()["status"] == "SCHEDULED"

    response = await client.post(
        "/api/v1/games/cricket/predictions",
        headers={**test_env["headers"], "Idempotency-Key": "router-cricket-bet"},
        json={"match_id": "router-match", "selection": "HOME", "stake": 1_000},
    )
    assert response.status_code == 200
    assert response.json()["odds_bp"] == 200


@pytest.mark.asyncio
async def test_leaderboard_service_and_api(test_env):
    """Test leaderboard refresh and GET /leaderboard."""
    client = test_env["client"]
    headers = test_env["headers"]
    session_factory = test_env["session_factory"]

    # 1. Aggregate and refresh leaderboards
    async with session_factory() as session:
        svc = LeaderboardService(session)
        count = await svc.refresh_leaderboard(period="DAILY")
        assert count >= 1

    # 2. Query leaderboard API
    res = await client.get("/api/v1/leaderboard?period=DAILY", headers=headers)
    assert res.status_code == 200
    lb = res.json()
    assert len(lb) >= 1
    assert lb[0]["rank"] == 1
    assert lb[0]["total_won"] == 1250
