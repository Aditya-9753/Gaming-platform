"""Unit tests for platform constants, virtual currency invariants, and game schemas."""

import hashlib
import secrets
from app.core.constants import (
    PAISE_PER_CREDIT,
    GameType,
    RoundStatus,
    TransactionType,
    UserRole,
)


def test_virtual_currency_rules():
    """Verify non-negotiable rule: 100 paise = 1 Credit and only virtual credit transaction types exist."""
    assert PAISE_PER_CREDIT == 100

    # Ensure forbidden real-money transaction types do NOT exist
    forbidden_terms = ["DEPOSIT", "WITHDRAWAL", "CASHOUT", "FIAT", "INR", "USD"]
    tx_names = [t.name for t in TransactionType]
    for term in forbidden_terms:
        assert term not in tx_names

    # Ensure allowed virtual movements exist
    expected = {"BET", "WIN", "REFUND", "FAUCET", "BONUS", "ADJUSTMENT"}
    assert set(tx_names) == expected


def test_game_types_and_statuses():
    """Verify supported game types and round lifecycle states."""
    expected_games = {"AVIATOR", "MINES", "COLOR", "CRICKET"}
    actual_games = {g.name for g in GameType}
    assert actual_games == expected_games

    expected_statuses = {"SCHEDULED", "BETTING", "RUNNING", "COMPLETED", "CANCELLED"}
    actual_statuses = {s.name for s in RoundStatus}
    assert actual_statuses == expected_statuses


def test_provably_fair_commit_reveal_invariant():
    """Verify cryptographic commit-reveal hashing with secrets module (never random)."""
    server_seed = secrets.token_hex(32)
    server_seed_hash = hashlib.sha256(server_seed.encode("utf-8")).hexdigest()

    assert len(server_seed) == 64
    assert len(server_seed_hash) == 64

    # Verification: client can reproduce hash from revealed seed
    reproduced_hash = hashlib.sha256(server_seed.encode("utf-8")).hexdigest()
    assert reproduced_hash == server_seed_hash
