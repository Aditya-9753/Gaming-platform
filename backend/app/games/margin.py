"""One house margin per game, turned into that game's published payout table.

Every pick pays (1 - margin) / P(win), floored to 0.01x, so each pick returns
the same share of stakes in the long run. Only payouts change; outcomes stay
HMAC(server_seed, client_seed:nonce) and never look at the bets. Engines
snapshot the table when a round opens, so a change applies from the next round.

    Aviator, Mines : the margin is used directly by the multiplier formula
    WinGo          : payouts derived below (number 0-9, each 1 in 10)
    Color          : payouts derived below (RED/GREEN 9 in 19, VIOLET 1 in 19)
    Teen Patti     : winning side pays 2 x (1 - margin); ties refund every stake
    Cricket        : odds are set per match, so a single margin does not apply
"""

from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal
from fractions import Fraction
from typing import Any, Dict, Optional

# Payout config key each table-driven game reads, and P(win) for each pick
_WINGO_WIN_PROBABILITY: Dict[str, Fraction] = {
    # GREEN/RED pay full on 4 numbers and COLOR_HALF (3/4 rate) on the violet-shared one
    "GREEN": Fraction(19, 40),   # effective: 4/10 + 1/10 × 3/4
    "RED": Fraction(19, 40),
    "COLOR_HALF": Fraction(19, 30),  # paid at 3/4 of the GREEN/RED rate
    "VIOLET": Fraction(2, 10),
    "NUMBER": Fraction(1, 10),
    "SIZE": Fraction(5, 10),
}
_COLOR_WIN_PROBABILITY: Dict[str, Fraction] = {
    "RED": Fraction(9, 19),
    "GREEN": Fraction(9, 19),
    "VIOLET": Fraction(1, 19),
}

def supports_margin(game_id: str) -> bool:
    return game_id in ("aviator", "mines", "color", "teen_patti") or game_id.startswith("wingo_")


def _table(edge_bp: int, probabilities: Dict[str, Fraction]) -> Dict[str, float]:
    keep = Fraction(10_000 - edge_bp, 10_000)
    table: Dict[str, float] = {}
    for key, p in probabilities.items():
        exact = keep / p
        multiplier = (Decimal(exact.numerator) / Decimal(exact.denominator)).quantize(Decimal("0.01"), rounding=ROUND_FLOOR)
        if multiplier < 1:
            raise ValueError(f"Margin {edge_bp / 100:.2f}% is too high: {key} would pay below 1x")
        table[key] = float(multiplier)
    return table


def payout_config_for_margin(game_id: str, edge_bp: int) -> Optional[Dict[str, Any]]:
    """Config patch carrying the payout table for this margin (None if the game has no table)."""
    if not 0 <= edge_bp < 10_000:
        raise ValueError("Margin must be between 0% and 99.99%")
    if game_id.startswith("wingo_"):
        return {"payouts": _table(edge_bp, _WINGO_WIN_PROBABILITY)}
    if game_id == "color":
        return {"payout_multipliers": _table(edge_bp, _COLOR_WIN_PROBABILITY)}
    if game_id == "teen_patti":
        return {"payout": _table(edge_bp, {"payout": Fraction(1, 2)})["payout"]}
    return None
