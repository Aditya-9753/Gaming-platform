"""Provably-fair random-number utilities.

Design:
- Server seed generated with ``secrets.token_hex`` (CSPRNG, never ``random``).
- Commitment: SHA-256(server_seed) is published BEFORE any bets are placed.
- Derivation: HMAC-SHA256(key=server_seed, msg=f"{client_seed}:{nonce}")
  produces a 256-bit digest.  Numbers are derived by reading 4-byte chunks.
- Verification: player supplies server_seed after round; client recomputes
  the derivation and confirms it matches the committed hash.

All public API here is pure-function (no I/O, no DB) so it can be called from
any layer (service, rules, tests, simulation scripts).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import struct
from typing import List, Sequence


# ---------------------------------------------------------------------------
# Seed generation
# ---------------------------------------------------------------------------


def generate_server_seed(nbytes: int = 32) -> str:
    """Return a cryptographically random server seed (hex string, 64 chars by default)."""
    return secrets.token_hex(nbytes)


def hash_server_seed(server_seed: str) -> str:
    """Return SHA-256(server_seed) as a 64-char hex string (the public commitment)."""
    return hashlib.sha256(server_seed.encode()).hexdigest()


def verify_seed_commitment(server_seed: str, published_hash: str) -> bool:
    """Confirm that hash_server_seed(server_seed) == published_hash (timing-safe)."""
    computed = hash_server_seed(server_seed)
    return hmac.compare_digest(computed, published_hash)


# ---------------------------------------------------------------------------
# HMAC derivation
# ---------------------------------------------------------------------------


def _derive_hmac(server_seed: str, client_seed: str, nonce: int) -> bytes:
    """Compute HMAC-SHA256(key=server_seed, msg="{client_seed}:{nonce}").

    Returns the raw 32-byte digest.
    """
    msg = f"{client_seed}:{nonce}".encode()
    return hmac.new(server_seed.encode(), msg, hashlib.sha256).digest()


def derive_float(server_seed: str, client_seed: str, nonce: int) -> float:
    """Derive a uniformly distributed float in [0, 1) from the seed triple.

    Uses the first 4 bytes of the HMAC digest as a big-endian uint32, then
    divides by 2^32.  This gives 2^32 equally probable values.
    """
    digest = _derive_hmac(server_seed, client_seed, nonce)
    # Big-endian uint32 from first 4 bytes
    (uint32,) = struct.unpack(">I", digest[:4])
    return uint32 / (2**32)


def derive_floats(
    server_seed: str,
    client_seed: str,
    nonce: int,
    count: int,
) -> List[float]:
    """Derive ``count`` independent floats in [0, 1).

    Each float uses a separate 4-byte window of the HMAC digest (up to 8
    floats per call with 32-byte digest) or increments a sub-nonce for more.

    For ``count`` ≤ 8: reads 4-byte chunks from a single 32-byte digest.
    For ``count`` > 8: generates additional digests with nonce+1, nonce+2, …
    """
    results: List[float] = []
    extra_nonce = 0
    while len(results) < count:
        digest = _derive_hmac(server_seed, client_seed, nonce + extra_nonce)
        # Extract up to 8 uint32 values from one 32-byte digest
        for i in range(0, 32, 4):
            if len(results) >= count:
                break
            (uint32,) = struct.unpack(">I", digest[i : i + 4])
            results.append(uint32 / (2**32))
        extra_nonce += 1
    return results


def derive_int(
    server_seed: str,
    client_seed: str,
    nonce: int,
    lo: int,
    hi: int,
) -> int:
    """Derive a uniform integer in [lo, hi] (inclusive).

    Uses rejection sampling to eliminate modulo bias.
    """
    if lo > hi:
        raise ValueError(f"lo ({lo}) must be ≤ hi ({hi})")
    span = hi - lo + 1
    extra = 0
    while True:
        digest = _derive_hmac(server_seed, client_seed, nonce + extra)
        for i in range(0, 32, 4):
            (uint32,) = struct.unpack(">I", digest[i : i + 4])
            # Rejection sampling: discard values in the biased tail
            limit = (2**32 // span) * span
            if uint32 < limit:
                return lo + (uint32 % span)
        extra += 1


def derive_shuffled_indices(
    server_seed: str,
    client_seed: str,
    nonce: int,
    n: int,
) -> List[int]:
    """Return a Fisher-Yates shuffle of [0, n-1] seeded from the triple.

    Each swap position is derived via a separate ``derive_int`` call so
    the full permutation is deterministic and verifiable.
    """
    indices = list(range(n))
    for i in range(n - 1, 0, -1):
        j = derive_int(server_seed, client_seed, nonce + i, 0, i)
        indices[i], indices[j] = indices[j], indices[i]
    return indices
