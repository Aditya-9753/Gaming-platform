"""Pydantic schemas for the Mines game."""

from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class MinesStartRequest(BaseModel):
    """Payload to start a new Mines game session."""

    bet_amount: int = Field(..., gt=0, description="Wager in integer paise (100 = 1 credit)")
    mine_count: int = Field(3, ge=1, le=24, description="Number of hidden mines (1 to 24)")
    client_seed: Optional[str] = Field(None, min_length=1, max_length=128)
    idempotency_key: Optional[str] = Field(None, min_length=1, max_length=100)


class MinesRevealRequest(BaseModel):
    """Payload to reveal a tile in an active game."""

    tile_index: int = Field(..., ge=0, le=24, description="Tile index to reveal (0 to 24)")


class MinesCashoutRequest(BaseModel):
    """Payload to cash out an active game."""

    pass


class MinesActionRequest(BaseModel):
    """Single action endpoint request. The action-specific service validates fields."""

    action: Literal["start", "reveal", "cashout"]
    bet_amount: Optional[int] = Field(None, gt=0)
    mine_count: Optional[int] = Field(None, ge=1, le=24)
    client_seed: Optional[str] = Field(None, min_length=1, max_length=128)
    tile_index: Optional[int] = Field(None, ge=0, le=24)


class MinesSessionResponse(BaseModel):
    """Current state of a player's Mines game."""

    round_id: str
    entry_id: str
    bet_amount: int
    mine_count: int
    revealed_tiles: List[int]
    current_multiplier: float
    next_multiplier: Optional[float]
    current_payout: int
    status: str  # "IN_PROGRESS", "WON", "LOST"
    server_seed_hash: str
    mines: Optional[List[int]] = None  # Revealed only when session terminates
    server_seed: Optional[str] = None  # Revealed only when session terminates
