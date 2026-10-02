"""Color-prediction game rules — provably fair, pure functions.

Color Prediction Game
----------------------
Each round produces one of three possible colours: RED, GREEN, or VIOLET.
Payouts (on a 1-unit bet):
  - RED   → 2× (probability ≈ 47.37%)
  - GREEN → 2× (probability ≈ 47.37%)
  - VIOLET → 4.5× (probability ≈ 5.26%)

Colour derivation
-----------------
1. Compute r = derive_float(server_seed, client_seed, nonce) ∈ [0, 1)
2. Map to a colour using a fixed probability table that embeds the house edge:

   The table has 19 slots (to give clean probabilities):
     slots 0-8   → RED    (9 slots = 47.37%)
     slots 9-17  → GREEN  (9 slots = 47.37%)
     slot 18     → VIOLET (1 slot  =  5.26%)

3. slot = floor(r × 19)

House edge per colour:
  RED:    bet 100, win 200  → P(win) × payout = 0.4737 × 2.00 = 0.9474 → house edge = 5.26%
  GREEN:  same as RED
  VIOLET: bet 100, win 450  → 0.0526 × 4.50 = 0.2368, but total E = 0.9211 → house edge ≈ 7.89%

Blended EV (assuming equal distribution of bets):
  E = (9/19 × 2) + (9/19 × 2) + (1/19 × 4.5) = 36/19 + 4.5/19 = 40.5/19 ≈ 0.9474

That gives approximately 5.26% blended house edge.

To match the configured house_edge_bp (default 500 = 5.00%), payouts are scaled
proportionally.
"""

from __future__ import annotations

from enum import Enum
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

# Default payout multipliers (× 100, i.e. "basis points" of the bet)
# RED/GREEN pay 2.00x = 200 basis points; VIOLET pays 4.50x = 450 bp.
_RED_PAYOUT_X100: int = 200
_GREEN_PAYOUT_X100: int = 200
_VIOLET_PAYOUT_X100: int = 450

# Probability slots (out of 19)
_TOTAL_SLOTS: int = 19
_RED_SLOTS: int = 9     # slots 0–8
_GREEN_SLOTS: int = 9   # slots 9–17
_VIOLET_SLOTS: int = 1  # slot 18

DEFAULT_HOUSE_EDGE_BP: int = 526  # ~5.26% blended (closest to 5% with integer slots)


class ColourResult(str, Enum):
    RED = "RED"
    GREEN = "GREEN"
    VIOLET = "VIOLET"


class ColorOutcome(NamedTuple):
    colour: ColourResult
    slot: int          # 0-based slot (0..18)
    payout_x100: int   # payout multiplier × 100 for a winning bet on this colour


def compute_colour(
    server_seed: str,
    client_seed: str,
    nonce: int,
    payout_multipliers: dict | None = None,
) -> ColorOutcome:
    """Determine the colour result for a round.

    Returns a ``ColorOutcome`` with the colour, the raw slot (for verification),
    and the payout multiplier × 100 for a correct prediction.

    Args:
        server_seed: Secret seed (revealed after settlement).
        client_seed: Public per-round client seed.
        nonce:       Round number / counter.
    """
    from app.utils.rng import derive_float

    r = derive_float(server_seed, client_seed, nonce)
    slot = int(r * _TOTAL_SLOTS)  # 0..18

    if slot < _RED_SLOTS:
        return ColorOutcome(
            colour=ColourResult.RED,
            slot=slot,
            payout_x100=configured_payout_x100(ColourResult.RED, payout_multipliers),
        )
    elif slot < _RED_SLOTS + _GREEN_SLOTS:
        return ColorOutcome(
            colour=ColourResult.GREEN,
            slot=slot,
            payout_x100=configured_payout_x100(ColourResult.GREEN, payout_multipliers),
        )
    else:
        return ColorOutcome(
            colour=ColourResult.VIOLET,
            slot=slot,
            payout_x100=configured_payout_x100(ColourResult.VIOLET, payout_multipliers),
        )


def colour_win_payout_x100(colour: ColourResult) -> int:
    """Return the winning payout multiplier × 100 for a given colour prediction."""
    return {
        ColourResult.RED: _RED_PAYOUT_X100,
        ColourResult.GREEN: _GREEN_PAYOUT_X100,
        ColourResult.VIOLET: _VIOLET_PAYOUT_X100,
    }[colour]


def configured_payout_x100(
    colour: ColourResult,
    payout_multipliers: dict | None = None,
) -> int:
    """Return a validated payout multiplier in hundredths from game settings."""
    default = colour_win_payout_x100(colour)
    if not payout_multipliers or colour.value not in payout_multipliers:
        return default
    try:
        multiplier = Decimal(str(payout_multipliers[colour.value]))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid payout multiplier for {colour.value}") from exc
    if not multiplier.is_finite() or multiplier < 1:
        raise ValueError(f"Invalid payout multiplier for {colour.value}")
    return int(multiplier * 100)


def round_timing_seconds(config: dict | None) -> tuple[float, float]:
    """Return timer and lock cutoff durations from the game's settings."""
    config = config or {}
    timer_seconds = float(
        config.get("timer_length_seconds", config.get("round_duration_seconds", 30))
    )
    if "lock_before_end_seconds" in config:
        lock_before_end = float(config["lock_before_end_seconds"])
    elif "betting_window_seconds" in config:
        lock_before_end = timer_seconds - float(config["betting_window_seconds"])
    else:
        lock_before_end = 5.0
    if (
        timer_seconds <= 0
        or lock_before_end < 0
        or lock_before_end >= timer_seconds
    ):
        raise ValueError("Color round timing settings are invalid")
    return timer_seconds, lock_before_end


def simulate_house_edge(
    n_rounds: int,
    server_seed: str = "benchmark_seed",
    client_seed: str = "benchmark_client",
) -> dict:
    """Simulate n_rounds and return blended/per-colour house edge statistics.

    Models a player who always bets 100 paise on RED every round.
    """
    total_bet = n_rounds * 100
    total_payout = 0
    counts = {ColourResult.RED: 0, ColourResult.GREEN: 0, ColourResult.VIOLET: 0}

    for nonce in range(n_rounds):
        outcome = compute_colour(server_seed, client_seed, nonce)
        counts[outcome.colour] += 1
        if outcome.colour == ColourResult.RED:
            total_payout += outcome.payout_x100  # 200 paise for 100-paise bet

    rtp = total_payout / total_bet
    return {
        "rounds": n_rounds,
        "counts": {k.value: v for k, v in counts.items()},
        "freq": {k.value: v / n_rounds for k, v in counts.items()},
        "rtp_red_bets": rtp,
        "house_edge_percent": round((1 - rtp) * 100, 4),
    }
