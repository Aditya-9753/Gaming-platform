"""Unit tests for the 4 games (Aviator, Color, Mines, Cricket) and base engine systems."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.games.aviator.rules import compute_crash_point, crash_x100_to_float
from app.games.aviator.schemas import AviatorBetRequest, AviatorCashoutRequest
from app.games.color.rules import ColourResult, compute_colour
from app.games.cricket.rules import BallOutcomeType, compute_ball_outcome
from app.games.mines.rules import (
    TOTAL_TILES,
    compute_mines_multiplier,
    compute_mines_multiplier_bp,
    derive_mine_positions,
)
from app.games.base.state import can_transition, validate_transition
from app.core.exceptions import BadRequestException


def test_round_state_transitions():
    """Verify allowed and forbidden state transitions."""
    assert can_transition("SCHEDULED", "BETTING") is True
    assert can_transition("BETTING", "RUNNING") is True
    assert can_transition("RUNNING", "COMPLETED") is True
    assert can_transition("BETTING", "CANCELLED") is True

    # Invalid transitions
    assert can_transition("COMPLETED", "RUNNING") is False
    assert can_transition("COMPLETED", "BETTING") is False
    assert can_transition("CANCELLED", "RUNNING") is False

    with pytest.raises(BadRequestException):
        validate_transition("COMPLETED", "RUNNING")


def test_aviator_rules():
    """Verify Aviator crash point derivation."""
    seed = "test_server_seed"
    client = "test_client_seed"
    crash1 = compute_crash_point(seed, client, 1)
    crash2 = compute_crash_point(seed, client, 1)
    # Determinism
    assert crash1 == crash2
    assert crash1 >= 100  # at least 1.00x
    assert crash_x100_to_float(crash1) >= 1.00


def test_color_rules():
    """Verify Color Prediction outcomes and payouts."""
    seed = "test_color_seed"
    client = "test_color_client"
    outcome = compute_colour(seed, client, 1)
    assert outcome.colour in (ColourResult.RED, ColourResult.GREEN, ColourResult.VIOLET)
    assert 0 <= outcome.slot < 19
    if outcome.colour == ColourResult.VIOLET:
        assert outcome.payout_x100 == 450
    else:
        assert outcome.payout_x100 == 200


def test_cricket_rules():
    """Verify Cricket ball delivery outcome."""
    seed = "test_cricket_seed"
    client = "test_cricket_client"
    ball = compute_ball_outcome(seed, client, 1)
    assert ball.outcome_type in list(BallOutcomeType)
    assert ball.payout_bp > 100
    assert 0 <= ball.slot < 100
    if ball.outcome_type == BallOutcomeType.WICKET:
        assert ball.is_wicket is True
        assert ball.runs == 0


def test_mines_rules_positions():
    """Verify deterministic 5x5 mine position derivation."""
    seed = "mines_seed_123"
    client = "mines_client_abc"
    nonce = 42
    mines = derive_mine_positions(seed, client, nonce, 5)
    assert len(mines) == 5
    assert all(0 <= m < TOTAL_TILES for m in mines)

    # Determinism
    mines_again = derive_mine_positions(seed, client, nonce, 5)
    assert mines == mines_again


def test_mines_multiplier_progression():
    """Verify Mines multiplier scales upward with safe picks and respects house edge."""
    mine_count = 3
    mult1 = compute_mines_multiplier(1, mine_count)
    mult2 = compute_mines_multiplier(2, mine_count)
    mult3 = compute_mines_multiplier(3, mine_count)

    assert mult1 >= 1.0
    assert mult2 > mult1
    assert mult3 > mult2

    bp1 = compute_mines_multiplier_bp(1, mine_count)
    assert bp1 == int(round(mult1 * 100))


@pytest.mark.asyncio
async def test_leader_election_lifecycle():
    """Test Redis distributed leader election acquire, renew, release."""
    from app.games.base.leader import LeaderElection

    mock_redis = MagicMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.eval = AsyncMock(return_value=1)

    election = LeaderElection(mock_redis, "test_lock", ttl_seconds=10)
    assert election.is_leader is False

    acquired = await election.acquire()
    assert acquired is True
    assert election.is_leader is True

    renewed = await election.renew()
    assert renewed is True

    await election.release()
    assert election.is_leader is False
