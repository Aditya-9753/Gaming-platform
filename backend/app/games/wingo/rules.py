"""WinGo (colour / number / big-small) rules — provably fair, pure functions.

Each period draws one number 0..9 from HMAC(server_seed, client_seed:nonce):

    number : 0  1  2  3  4  5  6  7  8  9
    colour : R  G  R  G  R  G  R  G  R  G      (0 and 5 are also VIOLET)
             +V             +V
    size   : SMALL (0-4) / BIG (5-9)

Default payouts (multiplier on stake, configurable via settings.config.payouts):

    GREEN   2x   (1.5x when the number is 5)
    RED     2x   (1.5x when the number is 0)
    VIOLET  4.5x (0 or 5)
    NUMBER  9x   (exact number)
    BIG / SMALL 1.96x

Return-to-player: GREEN/RED 95%, VIOLET 90%, NUMBER 90%, BIG/SMALL 98%.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, NamedTuple, Optional, Tuple

GREEN, RED, VIOLET = "GREEN", "RED", "VIOLET"
BIG, SMALL = "BIG", "SMALL"
BET_COLOR, BET_NUMBER, BET_SIZE = "COLOR", "NUMBER", "SIZE"

DEFAULT_PAYOUTS: Dict[str, float] = {
    "GREEN": 2.0,
    "RED": 2.0,
    "COLOR_HALF": 1.5,  # GREEN on 5 / RED on 0
    "VIOLET": 4.5,
    "NUMBER": 9.0,
    "SIZE": 1.96,
}

# Game modes: game_id -> (round length seconds, lock seconds before draw, label, period code)
MODES: Dict[str, Tuple[int, int, str, int]] = {
    "wingo_30s": (30, 5, "WinGo 30sec", 1),
    "wingo_1m": (60, 5, "WinGo 1 Min", 2),
    "wingo_3m": (180, 5, "WinGo 3 Min", 3),
    "wingo_5m": (300, 5, "WinGo 5 Min", 4),
}


class WingoOutcome(NamedTuple):
    number: int
    colours: Tuple[str, ...]
    size: str


def number_colours(number: int) -> Tuple[str, ...]:
    if number == 0:
        return (RED, VIOLET)
    if number == 5:
        return (GREEN, VIOLET)
    return (GREEN,) if number % 2 else (RED,)


def number_size(number: int) -> str:
    return BIG if number >= 5 else SMALL


def compute_outcome(server_seed: str, client_seed: str, nonce: int) -> WingoOutcome:
    from app.utils.rng import derive_float

    number = min(9, int(derive_float(server_seed, client_seed, nonce) * 10))
    return WingoOutcome(number=number, colours=number_colours(number), size=number_size(number))


def payouts_from_config(config: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """Validated payout table in hundredths (x100)."""
    merged = dict(DEFAULT_PAYOUTS)
    merged.update((config or {}).get("payouts") or {})
    table: Dict[str, int] = {}
    for key, value in merged.items():
        try:
            multiplier = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid WinGo payout for {key}") from exc
        if not multiplier.is_finite() or multiplier < 1 or multiplier > 100:
            raise ValueError(f"Invalid WinGo payout for {key}")
        table[key] = int(multiplier * 100)
    return table


def normalise_selection(bet_type: str, value: Any) -> Tuple[str, str]:
    """Validate a selection; returns (TYPE, VALUE) or raises ValueError."""
    bet_type = str(bet_type).upper()
    if bet_type == BET_COLOR:
        colour = str(value).upper()
        if colour not in (GREEN, RED, VIOLET):
            raise ValueError("Colour must be GREEN, RED or VIOLET")
        return bet_type, colour
    if bet_type == BET_NUMBER:
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Number must be 0-9") from exc
        if not 0 <= number <= 9:
            raise ValueError("Number must be 0-9")
        return bet_type, str(number)
    if bet_type == BET_SIZE:
        size = str(value).upper()
        if size not in (BIG, SMALL):
            raise ValueError("Size must be BIG or SMALL")
        return bet_type, size
    raise ValueError("Bet type must be COLOR, NUMBER or SIZE")


def payout_x100(bet_type: str, value: str, outcome: WingoOutcome, payouts: Dict[str, int]) -> int:
    """Multiplier x100 paid for this selection (0 = lost)."""
    if bet_type == BET_NUMBER:
        return payouts["NUMBER"] if int(value) == outcome.number else 0
    if bet_type == BET_SIZE:
        return payouts["SIZE"] if value == outcome.size else 0
    if value == VIOLET:
        return payouts["VIOLET"] if VIOLET in outcome.colours else 0
    if value in outcome.colours:
        # The violet-shared numbers pay the reduced rate on GREEN / RED
        return payouts["COLOR_HALF"] if VIOLET in outcome.colours else payouts[value]
    return 0
