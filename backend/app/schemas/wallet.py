"""Wallet Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class WalletResponse(BaseModel):
    id: str
    user_id: str
    balance: int
    locked_balance: int
    available_balance: int  # computed: balance - locked_balance
    currency: str
    is_frozen: bool
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, wallet) -> "WalletResponse":  # type: ignore[override]
        return cls(
            id=wallet.id,
            user_id=wallet.user_id,
            balance=wallet.balance,
            locked_balance=wallet.locked_balance,
            available_balance=wallet.balance - wallet.locked_balance,
            currency=wallet.currency,
            is_frozen=wallet.is_frozen,
            updated_at=wallet.updated_at,
        )


class WalletTransactionResponse(BaseModel):
    id: str
    wallet_id: str
    idempotency_key: str
    type: str
    amount: int
    balance_before: int
    balance_after: int
    status: str
    reference: Optional[str]
    description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class DailyClaimResponse(BaseModel):
    message: str
    transaction: WalletTransactionResponse
    new_balance: int
    cooldown_remaining_seconds: int


class AdminAdjustRequest(BaseModel):
    target_user_id: str
    amount_paise: int
    reason: str
    idempotency_key: str
