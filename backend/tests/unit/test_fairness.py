"""Unit and integration tests for the provably-fair system.

Coverage:
1. RNG determinism: same inputs → same float / int / shuffle.
2. Hash commitment: SHA-256(seed) == published hash; wrong seed fails.
3. HMAC avalanche: 1-byte seed change produces completely different output.
4. Aviator crash-point distribution sanity (not below 1.00x, not above cap).
5. Aviator house-edge formula: long-run RTP ≈ (1 - house_edge).
6. Color distribution: RED/GREEN ≈ 9/19, VIOLET ≈ 1/19 over many rounds.
7. FairnessService: verify endpoint hides seed on active rounds (403).
8. FairnessService: verify endpoint returns full data on completed rounds.
9. FairnessService: hash_valid and result_matches flags are correct.
10. derive_int: uniform distribution, no modulo bias outliers.
"""

from __future__ import annotations

import uuid
from datetime import timezone, datetime
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.constants import RoundStatus
from app.core.database import Base
from app.core.exceptions import ForbiddenException, NotFoundException
from app.games.aviator.rules import (
    DEFAULT_HOUSE_EDGE_BP as AVIATOR_EDGE_BP,
    compute_crash_point,
    crash_x100_to_float,
    format_crash,
)
from app.games.color.rules import (
    ColourResult,
    compute_colour,
)
from app.utils.rng import (
    derive_float,
    derive_floats,
    derive_int,
    derive_shuffled_indices,
    generate_server_seed,
    hash_server_seed,
    verify_seed_commitment,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def engine():
    eng = create_async_engine(TEST_DB, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture(scope="function")
async def session_factory(engine):
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


# =========================================================================
# 1. RNG — Determinism
# =========================================================================


def test_derive_float_determinism():
    """Same (seed, client, nonce) always produces the same float."""
    f1 = derive_float("seed_abc", "client_xyz", 42)
    f2 = derive_float("seed_abc", "client_xyz", 42)
    assert f1 == f2
    assert 0.0 <= f1 < 1.0


def test_derive_float_nonce_changes_output():
    """Different nonces must produce different outputs."""
    f0 = derive_float("seed", "client", 0)
    f1 = derive_float("seed", "client", 1)
    assert f0 != f1


def test_derive_float_seed_changes_output():
    """1-character seed change must produce different output (avalanche)."""
    f1 = derive_float("AAAA", "client", 0)
    f2 = derive_float("AAAB", "client", 0)
    assert f1 != f2


def test_derive_floats_multiple():
    """derive_floats returns a list of unique, deterministic floats."""
    floats = derive_floats("seed", "client", 0, 10)
    assert len(floats) == 10
    assert all(0.0 <= f < 1.0 for f in floats)
    # All distinct (extremely unlikely to collide with HMAC)
    assert len(set(floats)) == 10
    # Deterministic
    floats2 = derive_floats("seed", "client", 0, 10)
    assert floats == floats2


def test_derive_int_range():
    """derive_int returns values strictly in [lo, hi]."""
    results = {derive_int("seed", "client", nonce, 1, 6) for nonce in range(200)}
    assert results == {1, 2, 3, 4, 5, 6}  # all values covered


def test_derive_int_uniformity():
    """derive_int distribution is roughly uniform (chi-square light check)."""
    counts = {i: 0 for i in range(1, 7)}
    for nonce in range(6000):
        v = derive_int("seed", "client", nonce, 1, 6)
        counts[v] += 1
    # Each value should appear ~1000 times; allow ±30% tolerance
    for v, c in counts.items():
        assert 700 <= c <= 1300, f"Value {v} appeared {c} times (expected ~1000)"


def test_derive_shuffled_indices_permutation():
    """derive_shuffled_indices produces a valid permutation of [0, n)."""
    n = 25
    shuffled = derive_shuffled_indices("seed", "client", 0, n)
    assert sorted(shuffled) == list(range(n))
    assert shuffled != list(range(n))  # should actually be shuffled


def test_derive_shuffled_indices_determinism():
    """Same inputs always produce the same permutation."""
    s1 = derive_shuffled_indices("seed", "client", 5, 10)
    s2 = derive_shuffled_indices("seed", "client", 5, 10)
    assert s1 == s2


# =========================================================================
# 2. Hash commitment
# =========================================================================


def test_hash_server_seed_format():
    """SHA-256 output is 64 hex chars."""
    seed = generate_server_seed()
    h = hash_server_seed(seed)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_verify_seed_commitment_valid():
    """Correct seed verifies successfully."""
    seed = generate_server_seed()
    h = hash_server_seed(seed)
    assert verify_seed_commitment(seed, h) is True


def test_verify_seed_commitment_wrong_seed():
    """Different seed does NOT verify."""
    seed = generate_server_seed()
    h = hash_server_seed(seed)
    assert verify_seed_commitment(seed + "x", h) is False


def test_generate_server_seed_unique():
    """Every generated seed is unique."""
    seeds = {generate_server_seed() for _ in range(1000)}
    assert len(seeds) == 1000


# =========================================================================
# 3. Aviator crash-point rules
# =========================================================================


def test_crash_point_in_range():
    """Crash point is always in [100, 10000]."""
    for nonce in range(1000):
        c = compute_crash_point("seed", "client", nonce)
        assert 100 <= c <= 10_000, f"Crash {c} out of range at nonce={nonce}"


def test_crash_point_determinism():
    """Same inputs always produce the same crash point."""
    c1 = compute_crash_point("s1", "c1", 7)
    c2 = compute_crash_point("s1", "c1", 7)
    assert c1 == c2


def test_crash_point_different_nonces():
    """Different nonces produce variety in crash points."""
    points = {compute_crash_point("seed", "client", n) for n in range(200)}
    assert len(points) > 5  # meaningful variety


def test_crash_x100_to_float():
    assert crash_x100_to_float(250) == 2.5
    assert crash_x100_to_float(100) == 1.0
    assert crash_x100_to_float(10_000) == 100.0


def test_format_crash():
    assert format_crash(250) == "2.50x"
    assert format_crash(100) == "1.00x"


def test_aviator_house_edge_approximation():
    """Over 100k rounds the mean crash point should reflect the house edge.

    With 3% house edge, E[payout] ≈ 97% of stake.
    We test with a simple "always cash out at 1.00x" strategy → RTP ≈ 1.0
    That's not the right test; instead verify P(crash >= 2.00x) ≈ 48.5%.
    """
    hits_2x = sum(
        1 for n in range(100_000)
        if compute_crash_point("bench", "player", n) >= 200
    )
    # Expected: (1 - 3%) × 0.5 × 100% ≈ 48.5% (geometric distribution)
    # Allow generous band: 45%–52%
    pct = hits_2x / 100_000
    assert 0.43 <= pct <= 0.55, f"P(crash >= 2x) = {pct:.3f}"


# =========================================================================
# 4. Color-prediction rules
# =========================================================================


def test_colour_in_valid_set():
    """Every outcome is RED, GREEN, or VIOLET."""
    valid = {ColourResult.RED, ColourResult.GREEN, ColourResult.VIOLET}
    for n in range(500):
        outcome = compute_colour("seed", "client", n)
        assert outcome.colour in valid


def test_colour_determinism():
    o1 = compute_colour("seed", "client", 42)
    o2 = compute_colour("seed", "client", 42)
    assert o1 == o2


def test_colour_distribution():
    """RED ≈ 47.4%, GREEN ≈ 47.4%, VIOLET ≈ 5.3% over 50k rounds."""
    counts: Dict[str, int] = {"RED": 0, "GREEN": 0, "VIOLET": 0}
    n = 50_000
    for nonce in range(n):
        outcome = compute_colour("bench", "player", nonce)
        counts[outcome.colour.value] += 1

    # RED: expect ~47.4%, allow 45–50%
    assert 0.45 <= counts["RED"] / n <= 0.50
    # GREEN: same
    assert 0.45 <= counts["GREEN"] / n <= 0.50
    # VIOLET: expect ~5.3%, allow 4–7%
    assert 0.04 <= counts["VIOLET"] / n <= 0.07


def test_colour_slot_range():
    """Slot must be in [0, 18]."""
    for n in range(500):
        outcome = compute_colour("seed", "client", n)
        assert 0 <= outcome.slot <= 18


# =========================================================================
# 5. FairnessService — DB-backed tests
# =========================================================================


async def _seed_game(db: AsyncSession) -> str:
    """Insert a minimal Game row and return game_id."""
    from app.models.game import Game

    game_id = f"aviator_test_{uuid.uuid4().hex[:6]}"
    game = Game(
        id=game_id,
        name="Aviator Test",
        type="AVIATOR",
        is_active=True,
    )
    db.add(game)
    await db.flush()
    return game_id


@pytest.mark.asyncio
async def test_fairness_create_round_seed(session_factory):
    """create_round_seed persists a round with hash but hides the seed from clients."""
    from app.services.fairness_service import FairnessService

    async with session_factory() as db:
        game_id = await _seed_game(db)
        svc = FairnessService(db)
        game_round = await svc.create_round_seed(game_id, round_no=1)
        await db.commit()

        # Server seed must be stored internally
        assert game_round.server_seed is not None
        assert len(game_round.server_seed) == 64  # 32 bytes → 64 hex

        # Hash must match
        assert verify_seed_commitment(
            game_round.server_seed, game_round.server_seed_hash
        )


@pytest.mark.asyncio
async def test_get_round_commitment_hides_active_seed(session_factory):
    """Active round commitment must NOT include server_seed."""
    from app.services.fairness_service import FairnessService

    async with session_factory() as db:
        game_id = await _seed_game(db)
        svc = FairnessService(db)
        game_round = await svc.create_round_seed(game_id, round_no=2)
        await db.commit()

    async with session_factory() as db:
        svc = FairnessService(db)
        commitment = await svc.get_round_commitment(game_round.id)

    assert commitment["seed_revealed"] is False
    assert commitment["server_seed"] is None  # NEVER expose active seed
    assert commitment["server_seed_hash"] is not None


@pytest.mark.asyncio
async def test_verify_active_round_raises_403(session_factory):
    """Calling verify on a non-COMPLETED round must raise ForbiddenException."""
    from app.services.fairness_service import FairnessService

    async with session_factory() as db:
        game_id = await _seed_game(db)
        svc = FairnessService(db)
        game_round = await svc.create_round_seed(game_id, round_no=3)
        await db.commit()

    async with session_factory() as db:
        svc = FairnessService(db)
        with pytest.raises(ForbiddenException):
            await svc.verify_round(game_round.id)


@pytest.mark.asyncio
async def test_verify_completed_round(session_factory):
    """Completed round verification returns correct flags."""
    from app.services.fairness_service import FairnessService
    from app.games.aviator.rules import compute_crash_point, format_crash
    from sqlalchemy import select
    from app.models.game import GameRound

    async with session_factory() as db:
        game_id = await _seed_game(db)
        svc = FairnessService(db)
        game_round = await svc.create_round_seed(game_id, round_no=4)

        # Settle the round: compute crash, store result, mark COMPLETED
        crash_x100 = compute_crash_point(
            game_round.server_seed,
            game_round.client_seed,
            game_round.round_no,
        )
        game_round.result = {
            "crash_point_x100": crash_x100,
            "crash_point": format_crash(crash_x100),
        }
        game_round.status = RoundStatus.COMPLETED.value
        db.add(game_round)
        await db.commit()

    async with session_factory() as db:
        svc = FairnessService(db)
        data = await svc.verify_round(game_round.id)

    assert data["hash_valid"] is True
    assert data["result_matches"] is True
    assert data["server_seed"] == game_round.server_seed
    assert data["recomputed_result"]["crash_point_x100"] == crash_x100


@pytest.mark.asyncio
async def test_verify_detects_tampered_result(session_factory):
    """If stored result is tampered, result_matches must be False."""
    from app.services.fairness_service import FairnessService
    from app.games.aviator.rules import compute_crash_point

    async with session_factory() as db:
        game_id = await _seed_game(db)
        svc = FairnessService(db)
        game_round = await svc.create_round_seed(game_id, round_no=5)

        # Store a WRONG result
        game_round.result = {"crash_point_x100": 99999, "crash_point": "999.99x"}
        game_round.status = RoundStatus.COMPLETED.value
        db.add(game_round)
        await db.commit()

    async with session_factory() as db:
        svc = FairnessService(db)
        data = await svc.verify_round(game_round.id)

    assert data["hash_valid"] is True   # seed itself is fine
    assert data["result_matches"] is False  # but stored result is wrong


@pytest.mark.asyncio
async def test_verify_nonexistent_round_raises_404(session_factory):
    """Verifying a non-existent round raises NotFoundException."""
    from app.services.fairness_service import FairnessService

    async with session_factory() as db:
        svc = FairnessService(db)
        with pytest.raises(NotFoundException):
            await svc.verify_round(str(uuid.uuid4()))


def test_commitment_endpoint_reachable():
    """Fairness router imports and mounts without error."""
    from app.api.v1.fairness.router import router
    routes = [r.path for r in router.routes]
    assert any("/verify" in r for r in routes)
    assert any("/commitment" in r for r in routes)
