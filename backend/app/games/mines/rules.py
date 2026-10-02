"""Mines game rules — provably-fair 5x5 grid calculation."""

from __future__ import annotations

from typing import List, Set
from math import comb

from app.utils.rng import derive_shuffled_indices

TOTAL_TILES: int = 25
MIN_MINES: int = 1
MAX_MINES: int = 24
DEFAULT_HOUSE_EDGE_BP: int = 300  # 3.00%


def derive_mine_positions(
    server_seed: str,
    client_seed: str,
    nonce: int,
    mine_count: int,
) -> Set[int]:
    """Derive deterministic mine tile indices in range [0, 24].

    Uses HMAC-SHA256 Fisher-Yates shuffle. The first ``mine_count`` items
    in the permutation represent the mine positions.
    """
    if not (MIN_MINES <= mine_count <= MAX_MINES):
        raise ValueError(f"Mine count must be between {MIN_MINES} and {MAX_MINES}")

    permutation = derive_shuffled_indices(
        server_seed=server_seed,
        client_seed=client_seed,
        nonce=nonce,
        n=TOTAL_TILES,
    )
    return set(permutation[:mine_count])


def compute_mines_multiplier(
    revealed_count: int,
    mine_count: int,
    house_edge_bp: int = DEFAULT_HOUSE_EDGE_BP,
) -> float:
    """Compute payout multiplier for ``revealed_count`` safe picks.

    Formula:
        fair_multiplier = C(25, k) / C(25 - M, k)
        multiplier = (1 - house_edge) * fair_multiplier
    """
    safe_tiles = TOTAL_TILES - mine_count
    if not (0 <= revealed_count <= safe_tiles):
        raise ValueError("Revealed count cannot exceed number of safe tiles")
    if not 0 <= house_edge_bp < 10_000:
        raise ValueError("House edge must be between 0 and 9999 basis points")
    if revealed_count == 0:
        return 1.0
    if revealed_count > safe_tiles:
        raise ValueError("Revealed count cannot exceed number of safe tiles")

    return compute_mines_multiplier_bp(
        revealed_count, mine_count, house_edge_bp
    ) / 100


def compute_mines_multiplier_bp(
    revealed_count: int,
    mine_count: int,
    house_edge_bp: int = DEFAULT_HOUSE_EDGE_BP,
) -> int:
    """Return multiplier in basis points (e.g. 1.25x -> 125)."""
    if not (MIN_MINES <= mine_count <= MAX_MINES):
        raise ValueError(f"Mine count must be between {MIN_MINES} and {MAX_MINES}")
    safe_tiles = TOTAL_TILES - mine_count
    if not (0 <= revealed_count <= safe_tiles):
        raise ValueError("Revealed count cannot exceed number of safe tiles")
    if not 0 <= house_edge_bp < 10_000:
        raise ValueError("House edge must be between 0 and 9999 basis points")
    if revealed_count == 0:
        return 100

    numerator = comb(TOTAL_TILES, revealed_count) * 100 * (10_000 - house_edge_bp)
    denominator = comb(safe_tiles, revealed_count) * 10_000
    return max(100, numerator // denominator)
