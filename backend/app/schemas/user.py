"""User Pydantic schema (shared response object)."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool
    totp_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}
