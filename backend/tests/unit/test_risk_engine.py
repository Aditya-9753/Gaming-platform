"""Risk engine: family mapping, ceiling decisions, persistence and yield backtest."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.exceptions import BadRequestException
from app.models.game import Game, GameEntry, GameRound
from app.services import risk_engine

TEST_DB = "sqlite+aiosqlite:///:memory:"

OFF = {"status": "OFF", "target_hold_pct_bp": 1200, "max_round_pool_paise": 0, "max_player_round_paise": 0}
ON = {"status": "ON", "target_hold_pct_bp": 1200, "max_round_pool_paise": 5000, "max_player_round_paise": 2000}


# ------------------------------------------------------------ pure functions


def test_game_family_mapping():
    assert risk_engine.game_family("wingo_30s") == "wingo"
    assert risk_engine.game_family("wingo_5m") == "wingo"
    assert risk_engine.game_family("aviator") == "aviator"
    assert risk_engine.game_family("mines") == "mines"
    assert risk_engine.game_family("teen_patti") is None
    assert risk_engine.resolve_family("WinGo") == "wingo"
    assert risk_engine.resolve_family("mines") == "mines"
    with pytest.raises(BadRequestException):
        risk_engine.resolve_family("chess")


def test_evaluate_bet_off_uses_game_limits():
    ok = risk_engine.evaluate_bet(OFF, requested_paise=1000, game_min_bet=100, game_max_bet=5000)
    assert ok.allowed and ok.reason == "OK"
    high = risk_engine.evaluate_bet(OFF, requested_paise=9000, game_min_bet=100, game_max_bet=5000)
    assert not high.allowed and high.reason == "ABOVE_GAME_MAX_BET"
    low = risk_engine.evaluate_bet(OFF, requested_paise=50, game_min_bet=100, game_max_bet=5000)
    assert not low.allowed and low.reason == "BELOW_MIN_BET"


def test_evaluate_bet_on_enforces_round_and_player_ceilings():
    # Whole-round ceiling: 5000 cap, 4800 already staked -> only 200 accepted.
    decision = risk_engine.evaluate_bet(
        ON, requested_paise=1000, game_min_bet=100, game_max_bet=5000,
        round_pool_paise=4800, player_round_paise=0,
    )
    assert not decision.allowed and decision.reason == "ROUND_POOL_CAP"
    assert decision.effective_max_bet == 200 and decision.round_room == 200

    # Per-player ceiling: 2000 cap, this player already staked 2000.
    decision = risk_engine.evaluate_bet(
        ON, requested_paise=100, game_min_bet=100, game_max_bet=5000,
        round_pool_paise=0, player_round_paise=2000,
    )
    assert not decision.allowed and decision.reason == "PLAYER_ROUND_CAP"
    assert decision.player_room == 0

    # Within both ceilings -> accepted; effective max is the tightest room.
    decision = risk_engine.evaluate_bet(
        ON, requested_paise=1000, game_min_bet=100, game_max_bet=5000,
        round_pool_paise=1000, player_round_paise=500,
    )
    assert decision.allowed and decision.effective_max_bet == 1500


def test_build_game_reports_hold_and_verdict():
    controls = risk_engine.default_controls()
    reports = risk_engine.build_game_reports(
        [("wingo_1m", 2, 2000, 900), ("aviator", 1, 500, 500)], controls
    )
    wingo = reports["wingo_1m"]
    assert wingo["hold_pct"] == 55.0 and wingo["target_hold_pct"] == 8.3
    assert wingo["verdict"] == "above_target" and wingo["family"] == "wingo"
    assert reports["aviator"]["hold_pct"] == 0.0 and reports["aviator"]["verdict"] == "below_target"


# ------------------------------------------------------------ async / DB


@pytest.fixture
async def db():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_controls_defaults_toggle_and_persist(db):
    controls = await risk_engine.get_controls(db)
    assert controls["wingo"]["status"] == "OFF" and controls["wingo"]["target_hold_pct_bp"] == 830

    updated = await risk_engine.toggle_family(db, "wingo_3m", "ON", actor_id="admin")
    assert updated["wingo"]["status"] == "ON"
    await db.commit()

    assert (await risk_engine.get_controls(db))["wingo"]["status"] == "ON"


@pytest.mark.asyncio
async def test_update_controls_validation(db):
    with pytest.raises(BadRequestException):
        await risk_engine.update_controls(db, "chess", {"status": "ON"})
    with pytest.raises(BadRequestException):
        await risk_engine.update_controls(db, "wingo", {"status": "MAYBE"})
    with pytest.raises(BadRequestException):
        await risk_engine.update_controls(db, "wingo", {"nope": 1})
    with pytest.raises(BadRequestException):
        await risk_engine.update_controls(db, "wingo", {"max_round_pool_paise": -5})

    controls = await risk_engine.update_controls(
        db, "wingo", {"max_round_pool_paise": 5000, "target_hold_pct_bp": 1150}
    )
    assert controls["wingo"]["max_round_pool_paise"] == 5000
    assert controls["wingo"]["target_hold_pct_bp"] == 1150


async def _seed_activity(db: AsyncSession) -> None:
    db.add_all([
        Game(id="wingo_1m", name="WinGo 1 Min", type="COLOR"),
        Game(id="aviator", name="Aviator", type="AVIATOR"),
        Game(id="mines", name="Mines", type="MINES"),
    ])
    db.add_all([
        GameRound(id="r1", game_id="wingo_1m", round_no=1, status="HISTORY", server_seed_hash="h" * 64),
        GameRound(id="r2", game_id="aviator", round_no=1, status="COMPLETED", server_seed_hash="h" * 64),
        GameRound(id="r3", game_id="mines", round_no=1, status="COMPLETED", server_seed_hash="h" * 64),
    ])
    db.add_all([
        GameEntry(id="e1", round_id="r1", user_id="u1", bet_amount=1000, payout_amount=900, status="WON", idempotency_key="e1"),
        GameEntry(id="e2", round_id="r1", user_id="u2", bet_amount=1000, payout_amount=0, status="LOST", idempotency_key="e2"),
        GameEntry(id="e3", round_id="r2", user_id="u1", bet_amount=500, payout_amount=500, status="WON", idempotency_key="e3"),
        GameEntry(id="e4", round_id="r3", user_id="u1", bet_amount=2500, payout_amount=0, status="LOST", idempotency_key="e4"),
        GameEntry(id="e5", round_id="r3", user_id="u2", bet_amount=300, payout_amount=0, status="LOST", idempotency_key="e5"),
    ])
    await db.commit()


@pytest.mark.asyncio
async def test_yield_backtest_reports_hold_and_control_impact(db):
    await _seed_activity(db)
    await risk_engine.update_controls(
        db, "mines", {"status": "ON", "max_round_pool_paise": 2000, "max_player_round_paise": 1000}
    )
    await db.commit()

    report = await risk_engine.run_yield_backtest(db, days=30, max_rounds=100)
    await db.commit()

    wingo = report["games"]["wingo_1m"]
    assert wingo["wagered_paise"] == 2000 and wingo["paid_paise"] == 900
    assert wingo["hold_pct"] == 55.0 and wingo["target_hold_pct"] == 8.3
    assert report["games"]["aviator"]["hold_pct"] == 0.0
    assert report["totals"]["wagered_paise"] == 5300

    impact = report["control_impact"]["games"]["mines"]
    assert impact["rounds_over_pool_cap"] == 1            # pool 2800 > 2000
    assert impact["player_cap_breaches"] == 1             # u1 staked 2500 > 1000
    assert impact["would_decline_paise"] == (2800 - 2000) + (2500 - 1000)

    latest = await risk_engine.latest_backtest(db)
    assert latest["report"]["totals"]["wagered_paise"] == report["totals"]["wagered_paise"]
    assert latest["history"][0]["window_days"] == 30


@pytest.mark.asyncio
async def test_enforce_bet_off_allows_then_on_blocks(db):
    """The switch must actually gate real stakes: OFF passes, ON applies ceilings."""
    await _seed_activity(db)  # r1 (wingo_1m) already has a 2000-paise pool

    # OFF: the stake is allowed up to the game maximum.
    allowed = await risk_engine.enforce_bet(
        db, game_id="wingo_1m", user_id="u1", requested_paise=900_000,
        game_min_bet=100, game_max_bet=1_000_000, round_id="r1",
    )
    assert allowed.allowed

    # ON with a tight round ceiling: only 100 paise of room remains.
    await risk_engine.update_controls(
        db, "wingo", {"status": "ON", "max_round_pool_paise": 2100, "max_player_round_paise": 1500}
    )
    await db.commit()

    blocked = await risk_engine.enforce_bet(
        db, game_id="wingo_1m", user_id="u1", requested_paise=1000,
        game_min_bet=100, game_max_bet=1_000_000, round_id="r1",
    )
    assert not blocked.allowed and blocked.effective_max_bet == 100
    assert "staking limit" in risk_engine.limit_message(blocked)

    # A stake within the remaining room still goes through.
    small = await risk_engine.enforce_bet(
        db, game_id="wingo_1m", user_id="u1", requested_paise=100,
        game_min_bet=100, game_max_bet=1_000_000, round_id="r1",
    )
    assert small.allowed


@pytest.mark.asyncio
async def test_enforce_bet_solo_round_uses_caps(db):
    """Mines passes round_id=None (fresh solo round): the cap applies to the bet itself."""
    await risk_engine.update_controls(
        db, "mines", {"status": "ON", "max_round_pool_paise": 1000, "max_player_round_paise": 0}
    )
    await db.commit()

    blocked = await risk_engine.enforce_bet(
        db, game_id="mines", user_id="u1", requested_paise=5000,
        game_min_bet=100, game_max_bet=100_000, round_id=None,
    )
    assert not blocked.allowed and blocked.effective_max_bet == 1000

    ok = await risk_engine.enforce_bet(
        db, game_id="mines", user_id="u1", requested_paise=900,
        game_min_bet=100, game_max_bet=100_000, round_id=None,
    )
    assert ok.allowed