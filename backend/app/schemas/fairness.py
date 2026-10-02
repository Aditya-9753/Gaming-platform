"""Fairness / provably-fair Pydantic schemas."""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel


class RoundCommitmentResponse(BaseModel):
    """Public commitment data for any round (active or settled)."""

    round_id: str
    game_id: str
    round_no: int
    status: str
    server_seed_hash: str
    server_seed: Optional[str] = None  # None for active rounds
    client_seed: Optional[str] = None  # None for active rounds
    seed_revealed: bool


class RoundVerifyResponse(BaseModel):
    """Full provably-fair verification payload (only for settled rounds)."""

    round_id: str
    game_id: str
    round_no: int
    server_seed_hash: str
    server_seed: str
    client_seed: str
    nonce: int
    stored_result: Dict[str, Any]
    recomputed_result: Dict[str, Any]
    hash_valid: bool
    result_matches: bool
