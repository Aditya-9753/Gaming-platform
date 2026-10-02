"""Pydantic schemas for Cricket game."""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

from app.games.cricket.rules import BallOutcomeType


class CricketBetRequest(BaseModel):
    """Payload to place a bet on the next delivery."""

    round_id: str = Field(..., description="Target round ID")
    amount: int = Field(..., gt=0, description="Wager in integer paise (100 = 1 credit)")
    prediction: BallOutcomeType = Field(..., description="Predicted delivery outcome")
    idempotency_key: Optional[str] = Field(None, description="Optional client idempotency key")


class CricketBetResponse(BaseModel):
    """Response confirming cricket bet placement."""

    entry_id: str
    round_id: str
    bet_amount: int
    prediction: str
    status: str


class CricketRoundState(BaseModel):
    """Current state of a Cricket ball round."""

    round_id: str
    round_no: int
    status: str
    server_seed_hash: str
    outcome: Optional[str] = None
    runs: Optional[int] = None
    is_wicket: Optional[bool] = None


class CricketPredictionRequest(BaseModel):
    match_id: str = Field(..., min_length=1, max_length=100)
    selection: Literal["HOME", "AWAY"]
    stake: int = Field(..., gt=0)


class CricketSettlementOverrideRequest(BaseModel):
    winner: Optional[str] = Field(None, min_length=1, max_length=150)
    abandoned: bool = False
    reason: str = Field(..., min_length=5, max_length=500)
