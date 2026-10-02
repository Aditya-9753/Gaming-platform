"""Pydantic schemas for the Color Prediction game."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

from app.games.color.rules import ColourResult


class ColorBetRequest(BaseModel):
    """Payload to place a wager on a color outcome."""

    round_id: str = Field(..., description="Target round ID")
    amount: int = Field(..., gt=0, description="Bet amount in integer paise (100 = 1 credit)")
    colour: ColourResult = Field(..., description="Predicted color: RED, GREEN, or VIOLET")
    idempotency_key: Optional[str] = Field(None, description="Optional idempotency key")


class ColorActionRequest(BaseModel):
    """Place a Color Prediction wager through the idempotent action endpoint."""

    round_id: str
    amount: int = Field(..., gt=0, description="Bet amount in integer paise")
    colour: ColourResult


class ColorBetResponse(BaseModel):
    """Response confirming color bet placement."""

    entry_id: str
    round_id: str
    bet_amount: int
    colour: str
    status: str


class ColorRoundState(BaseModel):
    """Current state of a Color Prediction round."""

    round_id: str
    round_no: int
    status: str
    server_seed_hash: str
    winning_colour: Optional[str] = None
    slot: Optional[int] = None
