"""Aviator crash-point rules — provably fair, pure functions.

Crash point derivation algorithm
---------------------------------
This mirrors the industry-standard Aviator / Bustabit formula:

1. Compute h = HMAC-SHA256(key=server_seed, msg="{client_seed}:{nonce}")
2. Convert the first 8 hex characters (32 bits) to integer E.
3. Apply the house-edge formula:

       If E % HOUSE_MODULUS == 0 → crash = 1.00x  (instant crash, prob = 1/HOUSE_MODULUS)
       Else:
           crash = PAYOUT_BASE / (1 - E / 2^32)    ... capped at MAX_CRASH

   With house_edge_percent in basis points (e.g. 300 bp = 3.00%):
       HOUSE_MODULUS = floor(100_00 / house_edge_bp)
       PAYOUT_BASE   = (HOUSE_MODULUS - 1) / HOUSE_MODULUS × BASE_MULTIPLIER

4. Result rounded DOWN to 2 decimal places (platform-favourable).

The formula guarantees:
   E[crash] = PAYOUT_BASE / (1 - 1/HOUSE_MODULUS)^(-1)
            = 1 / (1 - house_edge_bp / 10_000)

Verifiable by the player: they supply server_seed after round settlement and
recompute with the same (client_seed, nonce).
"""

from __future__ import annotations

import hashlib
import hmac
import math
import struct
from datetime import datetime

# Platform default: 3.00% house edge (300 basis points)
DEFAULT_HOUSE_EDGE_BP: int = 300

# Maximum crash multiplier cap (100x)
MAX_CRASH_X100: int = 10_000  # 100.00x in basis points
MIN_CRASH_X100: int = 100     # 1.00x

# Internal resolution: we work in integer "centimultipliers" (x100)
# 1.00x → 100,  2.50x → 250,  100.00x → 10000
_UINT32_MAX: int = 2**32


def _crash_from_float(r: float, house_edge_bp: int) -> int:
    """Derive crash multiplier (x100 integer) from a uniform [0,1) float.

    Uses the standard provably-fair Aviator formula.
    Returns an integer in [100, MAX_CRASH_X100] (representing 1.00x … 100.00x).
    """
    # house_modulus: inverse of instant-crash probability
    # house_edge_bp = 300 → modulus = 33 → P(instant) ≈ 3.03%
    house_modulus = 10_000 // house_edge_bp if house_edge_bp else None

    # 1/house_modulus chance of instant crash at 1.00x
    # We simulate this by checking if the discrete uniform equivalent is 0
    discrete = int(r * _UINT32_MAX)
    if house_modulus and discrete % house_modulus == 0:
        return MIN_CRASH_X100

    # Standard crash formula: payout = (1 - house_edge) / (1 - r)
    # Scaled to basis points and capped
    safe_r = min(r, 1.0 - 1e-9)  # prevent division by zero
    raw = (10_000 - house_edge_bp) / (10_000 * (1.0 - safe_r)) * 100
    # Floor to 2 decimal places (x100 integer means 1 decimal = 1 unit here)
    result = int(raw)  # integer truncation = floor
    return max(MIN_CRASH_X100, min(result, MAX_CRASH_X100))


def compute_crash_point(
    server_seed: str,
    client_seed: str,
    nonce: int,
    house_edge_bp: int = DEFAULT_HOUSE_EDGE_BP,
) -> int:
    """Compute the crash multiplier for an Aviator round.

    Returns an integer representing the crash point × 100.
    E.g. 250 = 2.50x, 100 = 1.00x, 10000 = 100.00x.

    Args:
        server_seed:    The secret server seed (revealed after round).
        client_seed:    Public client seed (can be any string the client provides).
        nonce:          Round counter to ensure unique output per round.
        house_edge_bp:  House edge in basis points (300 = 3.00%).

    Returns:
        Integer crash multiplier × 100 in range [100, 10000].
    """
    if not 0 <= house_edge_bp < 10_000:
        raise ValueError("House edge must be between 0 and 9999 basis points")
    from app.utils.rng import derive_float

    r = derive_float(server_seed, client_seed, nonce)
    return _crash_from_float(r, house_edge_bp)


def crash_x100_to_float(crash_x100: int) -> float:
    """Convert integer multiplier (250) to float (2.50)."""
    return crash_x100 / 100.0


def format_crash(crash_x100: int) -> str:
    """Human-readable crash point string: '2.50x'."""
    return f"{crash_x100_to_float(crash_x100):.2f}x"


# Growth curves
#   "power"       : m(t) = 1 + (rate * t) ** power   (legacy; very slow at high x)
#   "exponential" : m(t) = e ** (rate * t)           (classic crash curve)
# With the default exponential rate of 0.045/s the plane reaches 2x in ~15 s,
# 10x in ~51 s and the 100x cap in ~102 s.
GROWTH_MODEL_POWER = "power"
GROWTH_MODEL_EXPONENTIAL = "exponential"
DEFAULT_EXP_GROWTH_RATE = 0.045


def multiplier_x100_at(
    elapsed_seconds: float,
    growth_rate: float = 0.08,
    growth_power: float = 1.3,
    growth_model: str = GROWTH_MODEL_POWER,
) -> int:
    """Calculate the server-authoritative multiplier from elapsed server time."""
    if elapsed_seconds <= 0:
        return 100
    if growth_rate <= 0 or growth_power <= 0:
        raise ValueError("Growth parameters must be positive")
    if growth_model == GROWTH_MODEL_EXPONENTIAL:
        # Cap the exponent to avoid overflow on absurd elapsed values
        return max(100, int(math.exp(min(growth_rate * elapsed_seconds, 50.0)) * 100))
    return max(100, int((1.0 + (elapsed_seconds * growth_rate) ** growth_power) * 100))


def crash_elapsed_seconds(
    crash_x100: int,
    growth_rate: float = 0.08,
    growth_power: float = 1.3,
    growth_model: str = GROWTH_MODEL_POWER,
) -> float:
    """Return the elapsed time at which the published growth curve reaches crash."""
    if crash_x100 <= MIN_CRASH_X100:
        return 0.0
    if growth_rate <= 0 or growth_power <= 0:
        raise ValueError("Growth parameters must be positive")
    if growth_model == GROWTH_MODEL_EXPONENTIAL:
        return math.log(crash_x100 / 100.0) / growth_rate
    return (((crash_x100 / 100.0) - 1.0) ** (1.0 / growth_power)) / growth_rate


def elapsed_since(started_at: datetime, now: datetime) -> float:
    """Subtract timestamps while tolerating naive values returned by SQLite."""
    if started_at.tzinfo is None and now.tzinfo is not None:
        started_at = started_at.replace(tzinfo=now.tzinfo)
    elif now.tzinfo is None and started_at.tzinfo is not None:
        now = now.replace(tzinfo=started_at.tzinfo)
    return max(0.0, (now - started_at).total_seconds())


def simulate_house_edge(
    n_rounds: int,
    house_edge_bp: int = DEFAULT_HOUSE_EDGE_BP,
    server_seed: str = "benchmark_seed",
    client_seed: str = "benchmark_client",
) -> float:
    """Simulate n_rounds and return the realised RTP (Return to Player) as a float.

    Returned as a fraction (0.97 = 97% RTP = 3% house edge).
    Uses a unit bet of 100 (1.00x wins back 100).
    """
    total_bet = n_rounds * 100  # 1.00x unit bet per round
    total_payout = 0

    for nonce in range(n_rounds):
        crash = compute_crash_point(server_seed, client_seed, nonce, house_edge_bp)
        # A player who cashes out at exactly 1.00x always wins their bet back
        # For simulation purposes we model a random cashout between 1.00x and crash
        # using a uniform draw to get a realistic average payout.
        from app.utils.rng import derive_float
        cashout_r = derive_float(server_seed, client_seed + "_cashout", nonce)
        cashout = int(100 + cashout_r * (crash - 100))  # uniform in [100, crash)
        total_payout += cashout  # won back cashout/100 × 100 = cashout paise

    rtp = total_payout / total_bet
    return rtp
