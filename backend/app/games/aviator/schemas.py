"""Pydantic schemas for the Aviator game."""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class AviatorBetRequest(BaseModel):
    """Payload to place a bet in the current Aviator round."""

    round_id: str = Field(..., description="ID of the round to place bet in")
    amount: int = Field(..., gt=0, description="Wager amount in integer paise (e.g. 100 = 1 credit)")
    auto_cashout: Optional[float] = Field(
        None, ge=1.01, le=100.0, description="Optional target multiplier to auto-cashout (e.g. 2.00)"
    )
    idempotency_key: Optional[str] = Field(
        None, description="Optional client idempotency key"
    )


class AviatorActionRequest(BaseModel):
    """Bet or cash out through the idempotent Aviator action endpoint."""

    action: Literal["bet", "cashout"]
    round_id: str
    amount: Optional[int] = Field(None, gt=0)
    auto_cashout: Optional[float] = Field(None, ge=1.01, le=100.0)
    entry_id: Optional[str] = None


class AviatorBetResponse(BaseModel):
    """Response confirming wager placement."""

    entry_id: str
    round_id: str
    bet_amount: int
    status: str
    auto_cashout: Optional[float] = None


class AviatorCashoutRequest(BaseModel):
    """Payload to cash out an active bet."""

    round_id: str
    entry_id: str


class AviatorCashoutResponse(BaseModel):
    """Response returned upon successful cashout."""

    entry_id: str
    round_id: str
    multiplier: float
    payout_amount: int
    status: str


class AviatorRoundState(BaseModel):
    """Current state of an Aviator round."""

    round_id: str
    round_no: int
    status: str
    current_multiplier: float
    server_seed_hash: str
    crash_point: Optional[float] = None
