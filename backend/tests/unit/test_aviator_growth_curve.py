"""Aviator growth-curve models: exponential (default for new rounds) and legacy power."""

import math

import pytest

from app.games.aviator.rules import (
    DEFAULT_EXP_GROWTH_RATE,
    GROWTH_MODEL_EXPONENTIAL,
    GROWTH_MODEL_POWER,
    crash_elapsed_seconds,
    multiplier_x100_at,
)


@pytest.mark.parametrize("crash_x100", [101, 150, 200, 1_000, 10_000])
@pytest.mark.parametrize(
    "rate,power,model",
    [(0.06, 1.0, GROWTH_MODEL_EXPONENTIAL), (0.08, 1.3, GROWTH_MODEL_POWER)],
)
def test_crash_time_inverts_multiplier_curve(crash_x100, rate, power, model):
    at = crash_elapsed_seconds(crash_x100, rate, power, model)
    assert multiplier_x100_at(at + 1e-6, rate, power, model) >= crash_x100
    assert multiplier_x100_at(max(at - 0.05, 0), rate, power, model) < crash_x100


def test_exponential_curve_reaches_cap_in_reasonable_time():
    # 100x cap must be reached in under ~2 minutes so long flights never look stuck
    assert crash_elapsed_seconds(10_000, DEFAULT_EXP_GROWTH_RATE, 1.0, GROWTH_MODEL_EXPONENTIAL) < 120
    assert math.isclose(
        crash_elapsed_seconds(200, 0.06, 1.0, GROWTH_MODEL_EXPONENTIAL), math.log(2) / 0.06
    )


def test_default_model_is_legacy_power_for_old_rounds():
    assert multiplier_x100_at(10, 0.08, 1.3) == multiplier_x100_at(10, 0.08, 1.3, GROWTH_MODEL_POWER)
