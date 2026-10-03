"""Teen Patti rules — pure functions, provably fair.

Every round deals two 3-card hands, Player A and Player B, from one deck
shuffled by HMAC(server_seed, client_seed:nonce) (``derive_shuffled_indices``).
Cards are dealt alternately: A gets shuffled positions 0, 2, 4 and B gets 1, 3, 5.

Hand ranking (high to low):
    TRAIL (three of a kind) > PURE SEQUENCE (straight flush) > SEQUENCE
    > COLOR (flush) > PAIR > HIGH CARD
Sequences: A-K-Q is the highest, A-2-3 the second highest, then K-Q-J ...
Equal hands (same ranks, suits don't matter) are a TIE: every bet is refunded.

Players bet on A or B; a winning side pays ``payout`` x stake (default 1.96x).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from app.utils.rng import derive_shuffled_indices

GAME_ID = "teen_patti"
SIDE_A, SIDE_B, TIE = "A", "B", "TIE"
SIDES = (SIDE_A, SIDE_B)

# Round timing (seconds)
BETTING_SECONDS = 20
REVEAL_SECONDS = 5

DEFAULT_PAYOUT = 1.96

RANKS = "23456789TJQKA"  # index + 2 = rank value (2..14)
SUITS = "SHDC"  # spades, hearts, diamonds, clubs

TRAIL, PURE_SEQUENCE, SEQUENCE, COLOR, PAIR, HIGH_CARD = 6, 5, 4, 3, 2, 1
HAND_NAMES = {
    TRAIL: "Trail",
    PURE_SEQUENCE: "Pure Sequence",
    SEQUENCE: "Sequence",
    COLOR: "Color",
    PAIR: "Pair",
    HIGH_CARD: "High Card",
}


class TeenPattiOutcome(NamedTuple):
    player_a: List[str]
    player_b: List[str]
    hand_a: str
    hand_b: str
    winner: str  # "A" | "B" | "TIE"


def card_code(index: int) -> str:
    """Deck index 0..51 -> e.g. 'AS', 'TH' (T = ten)."""
    return f"{RANKS[index % 13]}{SUITS[index // 13]}"


def _rank(card: str) -> int:
    return RANKS.index(card[0]) + 2


def hand_key(cards: Sequence[str]) -> Tuple[int, Tuple[int, ...]]:
    """Comparable strength: (category, tie-break ranks). Higher wins."""
    ranks = sorted((_rank(c) for c in cards), reverse=True)
    flush = len({c[1] for c in cards}) == 1
    distinct = len(set(ranks))

    if distinct == 1:
        return TRAIL, (ranks[0],)

    straight_top: Optional[int] = None
    if ranks == [14, 3, 2]:
        straight_top = 15  # A-2-3: second only to A-K-Q
    elif distinct == 3 and ranks[0] - ranks[2] == 2:
        straight_top = 16 if ranks[0] == 14 else ranks[0]  # A-K-Q is the best sequence
    if straight_top is not None:
        return (PURE_SEQUENCE if flush else SEQUENCE), (straight_top,)

    if flush:
        return COLOR, tuple(ranks)
    if distinct == 2:
        pair = ranks[1]  # the middle card is always part of the pair
        kicker = ranks[0] if ranks[0] != pair else ranks[2]
        return PAIR, (pair, kicker)
    return HIGH_CARD, tuple(ranks)


def compute_outcome(server_seed: str, client_seed: str, nonce: int) -> TeenPattiOutcome:
    deck = derive_shuffled_indices(server_seed, client_seed, nonce, 52)
    a = [card_code(i) for i in (deck[0], deck[2], deck[4])]
    b = [card_code(i) for i in (deck[1], deck[3], deck[5])]
    key_a, key_b = hand_key(a), hand_key(b)
    winner = SIDE_A if key_a > key_b else SIDE_B if key_b > key_a else TIE
    return TeenPattiOutcome(
        player_a=a,
        player_b=b,
        hand_a=HAND_NAMES[key_a[0]],
        hand_b=HAND_NAMES[key_b[0]],
        winner=winner,
    )


def payout_from_config(config: Optional[Dict[str, Any]]) -> int:
    """Winning-side multiplier in hundredths (x100), from settings.config.payout."""
    raw = (config or {}).get("payout", DEFAULT_PAYOUT)
    try:
        multiplier = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid Teen Patti payout") from exc
    if not multiplier.is_finite() or multiplier < 1 or multiplier > 10:
        raise ValueError("Invalid Teen Patti payout")
    return int(multiplier * 100)


def normalise_side(value: Any) -> str:
    side = str(value).strip().upper()
    if side not in SIDES:
        raise ValueError("Bet on A or B")
    return side
