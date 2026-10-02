"""WinGo rules: colours, payouts, RTP per bet type, validation and period ids."""

from datetime import datetime, timezone

import pytest

from app.games.wingo.engine import period_for
from app.games.wingo.rules import (
    WingoOutcome,
    compute_outcome,
    normalise_selection,
    number_colours,
    number_size,
    payout_x100,
    payouts_from_config,
)

PAYOUTS = payouts_from_config(None)


def outcome(n: int) -> WingoOutcome:
    return WingoOutcome(n, number_colours(n), number_size(n))


def test_number_colours_and_sizes():
    assert number_colours(0) == ("RED", "VIOLET")
    assert number_colours(5) == ("GREEN", "VIOLET")
    assert number_colours(7) == ("GREEN",)
    assert number_colours(8) == ("RED",)
    assert [number_size(n) for n in range(10)] == ["SMALL"] * 5 + ["BIG"] * 5


@pytest.mark.parametrize(
    "bet,value,drawn,expected",
    [
        ("COLOR", "GREEN", 3, 200),
        ("COLOR", "GREEN", 5, 150),  # shares with violet
        ("COLOR", "RED", 0, 150),
        ("COLOR", "RED", 3, 0),
        ("COLOR", "VIOLET", 0, 450),
        ("COLOR", "VIOLET", 4, 0),
        ("NUMBER", "7", 7, 900),
        ("NUMBER", "7", 8, 0),
        ("SIZE", "BIG", 5, 196),
        ("SIZE", "SMALL", 5, 0),
    ],
)
def test_payouts(bet, value, drawn, expected):
    assert payout_x100(bet, value, outcome(drawn), PAYOUTS) == expected


@pytest.mark.parametrize(
    "bet,value,rtp",
    [("COLOR", "GREEN", 0.95), ("COLOR", "RED", 0.95), ("COLOR", "VIOLET", 0.90),
     ("NUMBER", "3", 0.90), ("SIZE", "BIG", 0.98)],
)
def test_house_edge_per_bet_type(bet, value, rtp):
    expected = sum(payout_x100(bet, value, outcome(n), PAYOUTS) for n in range(10)) / 10 / 100
    assert expected == pytest.approx(rtp)


def test_draws_are_uniform_enough():
    counts = [0] * 10
    for nonce in range(5000):
        counts[compute_outcome("seed", "client", nonce).number] += 1
    assert min(counts) > 400 and max(counts) < 600


def test_selection_validation():
    assert normalise_selection("color", "green") == ("COLOR", "GREEN")
    assert normalise_selection("NUMBER", 4) == ("NUMBER", "4")
    assert normalise_selection("size", "small") == ("SIZE", "SMALL")
    for bad in [("COLOR", "BLUE"), ("NUMBER", "10"), ("SIZE", "HUGE"), ("ODD", "1")]:
        with pytest.raises(ValueError):
            normalise_selection(*bad)


def test_invalid_configured_payout_rejected():
    with pytest.raises(ValueError):
        payouts_from_config({"payouts": {"NUMBER": 0.5}})


def test_period_id_uses_ist_day_and_sequence():
    # 2026-10-02 00:00:30 IST == 2026-10-01 18:30:30 UTC -> second 30s slot of the IST day
    draw = datetime(2026, 10, 1, 18, 30, 30, tzinfo=timezone.utc)
    assert period_for(draw, 30, 1) == "20261002100001"
