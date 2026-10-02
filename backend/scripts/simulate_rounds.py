#!/usr/bin/env python
"""simulate_rounds.py — Provably-fair house-edge verification script.

Runs 1,000,000 simulated rounds for both Aviator and Color Prediction games
and prints the realised house-edge statistics.

Usage:
    cd backend
    python scripts/simulate_rounds.py

No database or Redis connection required — all calculations are pure functions.
"""

from __future__ import annotations

import sys
import time
from typing import Dict

# Make sure the backend package is importable
sys.path.insert(0, ".")

from app.games.aviator.rules import (
    DEFAULT_HOUSE_EDGE_BP as AVIATOR_EDGE_BP,
    compute_crash_point,
    crash_x100_to_float,
)
from app.games.color.rules import ColourResult, compute_colour
from app.utils.rng import derive_float

N_ROUNDS = 1_000_000
SERVER_SEED = "simulate_server_seed_v1"
CLIENT_SEED = "simulate_client_seed_v1"


# ---------------------------------------------------------------------------
# Aviator simulation
# ---------------------------------------------------------------------------


def simulate_aviator(n: int, house_edge_bp: int = AVIATOR_EDGE_BP) -> Dict:
    """Simulate n Aviator rounds.

    Strategy: player bets 100 paise on every round and cashes out at a random
    multiplier between 1.00x and the actual crash point.  The random cashout
    is derived from the same seed infrastructure to be verifiable.
    """
    print(f"\n{'=' * 60}")
    print(f"AVIATOR SIMULATION  —  {n:,} rounds  (house edge: {house_edge_bp / 100:.2f}%)")
    print("=" * 60)

    total_bet_paise = 0
    total_payout_paise = 0
    instant_crash = 0          # crash at 1.00x
    crash_buckets: Dict[str, int] = {
        "1.00x":   0,
        "1.01–1.99x": 0,
        "2.00–4.99x": 0,
        "5.00–9.99x": 0,
        "10.00–99.99x": 0,
        "100.00x": 0,
    }

    t0 = time.perf_counter()

    for nonce in range(n):
        crash_x100 = compute_crash_point(SERVER_SEED, CLIENT_SEED, nonce, house_edge_bp)
        crash = crash_x100_to_float(crash_x100)

        # Random cashout in [1.00, crash] using verifiable RNG
        r = derive_float(SERVER_SEED, CLIENT_SEED + ":cashout", nonce)
        cashout = 1.0 + r * (crash - 1.0)

        bet = 100
        # cashout is a float multiplier (e.g. 1.73) — payout = bet × cashout
        payout = int(cashout * bet)  # integer truncation, platform-favourable

        total_bet_paise += bet
        total_payout_paise += payout

        # Bucket
        if crash_x100 == 100:
            crash_buckets["1.00x"] += 1
            instant_crash += 1
        elif crash_x100 < 200:
            crash_buckets["1.01–1.99x"] += 1
        elif crash_x100 < 500:
            crash_buckets["2.00–4.99x"] += 1
        elif crash_x100 < 1000:
            crash_buckets["5.00–9.99x"] += 1
        elif crash_x100 < 10_000:
            crash_buckets["10.00–99.99x"] += 1
        else:
            crash_buckets["100.00x"] += 1

    elapsed = time.perf_counter() - t0
    rtp = total_payout_paise / total_bet_paise
    house_edge_realised = (1 - rtp) * 100

    print(f"  Rounds simulated     : {n:>12,}")
    print(f"  Rounds/second        : {n / elapsed:>12,.0f}")
    print(f"  Total bet (paise)    : {total_bet_paise:>12,}")
    print(f"  Total payout (paise) : {total_payout_paise:>12,}")
    print(f"  Realised RTP         : {rtp:>12.4%}")
    print(f"  Realised house edge  : {house_edge_realised:>12.4f}%")
    print(f"  Target house edge    : {house_edge_bp / 100:>12.2f}%")
    print(f"  Instant crashes      : {instant_crash:>12,}  ({instant_crash / n:.2%})")
    print(f"\n  Crash distribution:")
    for label, count in crash_buckets.items():
        bar = "#" * int(count / n * 50)
        print(f"    {label:>16s} : {count:>8,}  ({count / n:5.2%})  {bar}")

    return {
        "n": n,
        "rtp": rtp,
        "house_edge_realised_pct": house_edge_realised,
        "house_edge_target_pct": house_edge_bp / 100,
    }


# ---------------------------------------------------------------------------
# Color simulation
# ---------------------------------------------------------------------------


def simulate_color(n: int) -> Dict:
    """Simulate n Color Prediction rounds.

    Strategy: always bet 100 paise on RED.
    """
    print(f"\n{'=' * 60}")
    print(f"COLOR PREDICTION SIMULATION  —  {n:,} rounds")
    print("=" * 60)

    counts: Dict[str, int] = {"RED": 0, "GREEN": 0, "VIOLET": 0}
    total_bet = n * 100     # always bet on RED
    total_payout = 0

    t0 = time.perf_counter()

    for nonce in range(n):
        outcome = compute_colour(SERVER_SEED, CLIENT_SEED, nonce)
        counts[outcome.colour.value] += 1
        if outcome.colour == ColourResult.RED:
            total_payout += outcome.payout_x100  # 200 for 100-paise bet

    elapsed = time.perf_counter() - t0
    rtp = total_payout / total_bet
    house_edge_realised = (1 - rtp) * 100

    print(f"  Rounds simulated     : {n:>12,}")
    print(f"  Rounds/second        : {n / elapsed:>12,.0f}")
    print(f"  Colour distribution:")
    for colour, count in counts.items():
        expected = {"RED": 9 / 19, "GREEN": 9 / 19, "VIOLET": 1 / 19}[colour]
        deviation = abs(count / n - expected)
        print(
            f"    {colour:>10s}: {count:>8,}  ({count / n:5.2%})"
            f"  expected {expected:5.2%}  deviation {deviation:.4f}"
        )
    print(f"\n  Strategy: always bet RED")
    print(f"  Total bet (paise)    : {total_bet:>12,}")
    print(f"  Total payout (paise) : {total_payout:>12,}")
    print(f"  Realised RTP         : {rtp:>12.4%}")
    print(f"  Realised house edge  : {house_edge_realised:>12.4f}%")
    print(f"  Theoretical edge     :       5.2632%  (9×2 + 9×2 + 1×4.5 / 19 = 40.5/19 ≈ 94.74% RTP)")

    return {
        "n": n,
        "counts": counts,
        "rtp": rtp,
        "house_edge_realised_pct": house_edge_realised,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("Virtual Gaming Platform — Provably-Fair House-Edge Simulation")
    print(f"Server seed : {SERVER_SEED}")
    print(f"Client seed : {CLIENT_SEED}")
    print(f"Rounds      : {N_ROUNDS:,}")

    aviator_result = simulate_aviator(N_ROUNDS)
    color_result = simulate_color(N_ROUNDS)

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    print(
        f"  Aviator  — realised edge: {aviator_result['house_edge_realised_pct']:.4f}%"
        f"  (target: {aviator_result['house_edge_target_pct']:.2f}%)"
    )
    print(
        f"  Color    — realised edge: {color_result['house_edge_realised_pct']:.4f}%"
        f"  (theoretical: 5.26%)"
    )

    # Exit non-zero if edge is wildly off
    aviator_ok = abs(aviator_result["house_edge_realised_pct"] - AVIATOR_EDGE_BP / 100) < 1.0
    color_ok = abs(color_result["house_edge_realised_pct"] - 5.26) < 1.0

    if not aviator_ok or not color_ok:
        print("\n[WARN] Realised house edge deviates > 1pp from theoretical!")
        sys.exit(1)
    else:
        print("\n[OK] Realised house edges are within 1pp of theoretical values.")
        sys.exit(0)
