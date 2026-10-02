"""Cricket game rules and provably-fair ball outcome derivation."""

from __future__ import annotations

from enum import Enum
from typing import Dict, NamedTuple

from app.utils.rng import derive_float


class BallOutcomeType(str, Enum):
    DOT = "DOT"              # 0 runs
    SINGLE = "SINGLE"        # 1 run
    DOUBLE = "DOUBLE"        # 2 runs
    FOUR = "FOUR"            # 4 runs
    SIX = "SIX"              # 6 runs
    WICKET = "WICKET"        # Out!


# Multiplier payout in basis points (100 = 1.00x)
OUTCOME_PAYOUTS_BP: Dict[BallOutcomeType, int] = {
    BallOutcomeType.DOT: 180,       # 1.80x
    BallOutcomeType.SINGLE: 220,    # 2.20x
    BallOutcomeType.DOUBLE: 400,    # 4.00x
    BallOutcomeType.FOUR: 550,      # 5.50x
    BallOutcomeType.SIX: 950,       # 9.50x
    BallOutcomeType.WICKET: 750,    # 7.50x
}

# 100-slot probability partition
# Dot: 30%, Single: 25%, Double: 15%, Four: 12%, Six: 8%, Wicket: 10%
# Sum = 100%
PROBABILITY_SLOTS = [
    (30, BallOutcomeType.DOT),
    (55, BallOutcomeType.SINGLE),
    (70, BallOutcomeType.DOUBLE),
    (82, BallOutcomeType.FOUR),
    (90, BallOutcomeType.SIX),
    (100, BallOutcomeType.WICKET),
]


class BallOutcome(NamedTuple):
    outcome_type: BallOutcomeType
    runs: int
    is_wicket: bool
    payout_bp: int
    slot: int


def compute_ball_outcome(
    server_seed: str,
    client_seed: str,
    nonce: int,
) -> BallOutcome:
    """Derive ball delivery outcome deterministically from provably fair seeds."""
    r = derive_float(server_seed, client_seed, nonce)
    slot = int(r * 100)  # 0 to 99

    for threshold, outcome_type in PROBABILITY_SLOTS:
        if slot < threshold:
            runs_map = {
                BallOutcomeType.DOT: 0,
                BallOutcomeType.SINGLE: 1,
                BallOutcomeType.DOUBLE: 2,
                BallOutcomeType.FOUR: 4,
                BallOutcomeType.SIX: 6,
                BallOutcomeType.WICKET: 0,
            }
            return BallOutcome(
                outcome_type=outcome_type,
                runs=runs_map[outcome_type],
                is_wicket=(outcome_type == BallOutcomeType.WICKET),
                payout_bp=OUTCOME_PAYOUTS_BP[outcome_type],
                slot=slot,
            )

    return BallOutcome(
        outcome_type=BallOutcomeType.WICKET,
        runs=0,
        is_wicket=True,
        payout_bp=OUTCOME_PAYOUTS_BP[BallOutcomeType.WICKET],
        slot=99,
    )
