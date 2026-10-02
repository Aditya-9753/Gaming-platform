"""Pydantic v2 schemas for authentication request/response payloads."""

from __future__ import annotations

import re
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


PASSWORD_MIN_LEN = 8
PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&_\-#^])[A-Za-z\d@$!%*?&_\-#^]{8,}$"
)

# Players: 8-128 characters with at least one letter and one number; any symbols allowed.
# Staff accounts keep the stricter PASSWORD_PATTERN above.
PLAYER_PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,128}$")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    email: Optional[EmailStr] = None
    password: str = Field(min_length=8, max_length=128)
    age_confirmed: bool

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not PLAYER_PASSWORD_PATTERN.match(v):
            raise ValueError("Password must be at least 8 characters with a letter and a number")
        return v

    @field_validator("age_confirmed")
    @classmethod
    def must_confirm_age(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must confirm you are of legal age to use this platform")
        return v


class LoginRequest(BaseModel):
    """Sign in with a username (or email) and password.

    ``username`` accepts either the username or the email address; the legacy
    ``email`` field is still accepted for older clients.
    """

    username: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = Field(None, min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)
    totp_code: Optional[str] = Field(None, min_length=6, max_length=6)

    @field_validator("totp_code", mode="before")
    @classmethod
    def blank_totp_is_none(cls, v: Optional[str]) -> Optional[str]:
        return v or None

    @model_validator(mode="after")
    def require_identifier(self) -> "LoginRequest":
        if not (self.username or self.email or "").strip():
            raise ValueError("Username is required")
        return self

    @property
    def identifier(self) -> str:
        return (self.username or self.email or "").strip()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token TTL in seconds")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not PASSWORD_PATTERN.match(v):
            raise ValueError(
                "Password must contain uppercase, lowercase, digit and special character"
            )
        return v


class TOTPSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class TOTPVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class MeResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool
    totp_enabled: bool
    requires_2fa_setup: bool = False
    two_factor_method: Optional[str] = None
    full_name: Optional[str] = None
    is_staff: bool = False
    permissions: list[str] = []

    model_config = {"from_attributes": True}
