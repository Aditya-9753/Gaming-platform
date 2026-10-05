"""Aviator crash formula v2: the configured house edge is the real edge (applied once)."""

from __future__ import annotations

import random

import pytest

from app.games.aviator.rules import (
    CRASH_FORMULA_V1,
    CRASH_FORMULA_V2,
    CURRENT_CRASH_FORMULA,
    _crash_from_float,
    compute_crash_point,
    crash_formula_of,
)
from app.services.hold_analyzer import aviator_rtp


def test_new_rounds_use_v2_and_old_rounds_stay_v1():
    assert CURRENT_CRASH_FORMULA == CRASH_FORMULA_V2
    assert crash_formula_of({"house_edge_bp": 300}) == CRASH_FORMULA_V1  # stored before versioning
    assert crash_formula_of(None) == CRASH_FORMULA_V1
    assert crash_formula_of({"crash_formula": 2}) == CRASH_FORMULA_V2


def test_v1_results_are_unchanged_for_verification():
    # Past rounds must keep verifying: default and explicit v1 give the same crash as before
    for nonce in range(200):
        assert compute_crash_point("seed", "client", nonce, 300) == compute_crash_point("seed", "client", nonce, 300, CRASH_FORMULA_V1)


def test_v2_differs_only_by_dropping_the_extra_instant_crash():
    for nonce in range(500):
        v1 = compute_crash_point("s", "c", nonce, 1000, CRASH_FORMULA_V1)
        v2 = compute_crash_point("s", "c", nonce, 1000, CRASH_FORMULA_V2)
        assert v1 == v2 or v1 == 100


@pytest.mark.parametrize("target", [150, 200, 500, 1000])
def test_v2_rtp_matches_configured_edge(target):
    rng = random.Random(target)
    n = 300_000
    wins = sum(1 for _ in range(n) if _crash_from_float(rng.random(), 1000, CRASH_FORMULA_V2) >= target)
    rtp = wins * target / 100 / n
    assert aviator_rtp(1000, target, CRASH_FORMULA_V2) == pytest.approx(0.90)
    assert rtp == pytest.approx(0.90, abs=0.012)
    # The legacy formula took roughly twice the edge
    assert aviator_rtp(1000, target, CRASH_FORMULA_V1) == pytest.approx(0.81)


def test_unknown_formula_is_rejected():
    with pytest.raises(ValueError):
        compute_crash_point("s", "c", 1, 300, 9)
