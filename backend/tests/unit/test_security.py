"""Unit tests for security functions: Argon2 password hashing and JWT tokens."""

import pytest
from pydantic import ValidationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.core.config import Settings


def test_argon2_password_hashing():
    """Verify Argon2 hashing and password verification."""
    password = "SuperSecurePassword#2026"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_token_hashing():
    """Verify SHA-256 token hashing produces consistent hex digests."""
    raw = "refresh_token_plain_text_123"
    h1 = hash_token(raw)
    h2 = hash_token(raw)
    assert h1 == h2
    assert len(h1) == 64


def test_jwt_access_and_refresh_tokens():
    """Verify JWT access and refresh token encoding and decoding."""
    payload = {"sub": "user-uuid-123", "role": "USER"}

    # Access Token
    access_token = create_access_token(payload)
    decoded_access = decode_access_token(access_token)
    assert decoded_access["sub"] == "user-uuid-123"
    assert decoded_access["role"] == "USER"
    assert decoded_access["type"] == "access"
    assert "exp" in decoded_access

    # Refresh Token
    refresh_token = create_refresh_token(payload)
    decoded_refresh = decode_refresh_token(refresh_token)
    assert decoded_refresh["sub"] == "user-uuid-123"
    assert decoded_refresh["type"] == "refresh"
    assert "exp" in decoded_refresh


def test_production_settings_reject_weak_or_development_secrets():
    with pytest.raises(ValidationError, match="JWT_SECRET must be a unique secret"):
        Settings(
            APP_ENV="production",
            DEBUG=False,
            JWT_SECRET="weak",
            JWT_REFRESH_SECRET="another-secret-that-is-long-enough-123",
            CORS_ORIGINS=["https://frontend.example"],
        )

    settings = Settings(
        APP_ENV="production",
        DEBUG=False,
        JWT_SECRET="jwt-secret-" + "a" * 40,
        JWT_REFRESH_SECRET="refresh-secret-" + "b" * 40,
        CORS_ORIGINS=["https://frontend.example"],
    )
    assert settings.is_production
