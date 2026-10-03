"""Application configuration using Pydantic Settings v2.

Loads environment variables from OS or .env file with comprehensive validation.
"""

from functools import lru_cache
from typing import List, Optional, Union
import secrets
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core application settings."""

    # Application
    APP_NAME: str = "Virtual Gaming Platform"
    APP_ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # Database (PostgreSQL Async)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/gaming_db"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT: int = 30

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CRICKET_DATA_URL: Optional[str] = None
    CRICKET_DATA_API_KEY: Optional[str] = None
    # Email (admin 2-step verification codes, password reset)
    EMAIL_PROVIDER: Optional[str] = None  # brevo | resend | smtp | console (auto by keys)
    EMAIL_FROM: Optional[str] = None
    EMAIL_FROM_NAME: str = "GameZone"
    BREVO_API_KEY: Optional[str] = None
    RESEND_API_KEY: Optional[str] = None
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    # Comma separated: only these addresses may receive admin login codes (empty = any)
    ADMIN_OTP_EMAILS: str = ""

    # AES-256-GCM key (64 hex characters) sealing ledger and audit rows against tampering
    AUDIT_ENCRYPTION_KEY: Optional[str] = None

    # Real worldwide cricket from CricketData.org (free key at cricketdata.org)
    CRICAPI_KEY: Optional[str] = None
    CRICAPI_LIVE_REFRESH_SECONDS: int = 1000
    CRICAPI_SCHEDULE_REFRESH_SECONDS: int = 10800

    # JWT Authentication
    JWT_SECRET: str = ""
    JWT_REFRESH_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # Monitoring
    SENTRY_DSN: Optional[str] = None

    # Virtual Credits (100 paise = 1 Credit)
    INITIAL_FAUCET_CREDITS: int = 10000
    PAISE_PER_CREDIT: int = 100

    # Admin security / local bootstrap
    # None = auto: 2FA enforced only in production.
    ADMIN_2FA_REQUIRED: Optional[bool] = None
    # Auto-seed roles, games and the hard-coded staff accounts on startup
    # (never runs in production).
    SEED_DEFAULT_ACCOUNTS: bool = True
    # Run game engines (Aviator, Color, Cricket feed) inside the API process.
    # None = auto: on outside production (production uses the separate worker).
    RUN_GAME_ENGINES: Optional[bool] = None
    # Bot accounts that genuinely play (live feeds / leaderboards).
    # None = auto: on outside production and tests.
    SIMULATED_PLAYERS: Optional[bool] = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        """Parse comma-delimited strings into a list of allowed origins."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Reject known development defaults and weak credentials in production."""
        if self.is_production:
            if self.DEBUG:
                raise ValueError("DEBUG must be false in production")
            for name in ("JWT_SECRET", "JWT_REFRESH_SECRET"):
                secret = getattr(self, name)
                if len(secret) < 32 or secret.startswith("replace-with-"):
                    raise ValueError(
                        f"{name} must be a unique secret of at least 32 characters in production"
                    )
            if any("localhost" in origin or "127.0.0.1" in origin for origin in self.CORS_ORIGINS):
                raise ValueError("Production CORS_ORIGINS must not include localhost")
        else:
            if not self.JWT_SECRET:
                object.__setattr__(self, "JWT_SECRET", secrets.token_urlsafe(48))
            if not self.JWT_REFRESH_SECRET:
                object.__setattr__(self, "JWT_REFRESH_SECRET", secrets.token_urlsafe(48))
        return self

    @property
    def is_production(self) -> bool:
        """Check if environment is set to production."""
        return self.APP_ENV.lower() == "production"

    @property
    def admin_2fa_required(self) -> bool:
        """Whether ADMIN / SUPERADMIN accounts must have TOTP enabled."""
        if self.ADMIN_2FA_REQUIRED is None:
            return self.is_production
        return self.ADMIN_2FA_REQUIRED

    @property
    def run_game_engines_in_api(self) -> bool:
        if self.RUN_GAME_ENGINES is None:
            return not self.is_production and not self.is_test
        return self.RUN_GAME_ENGINES

    @property
    def simulated_players_enabled(self) -> bool:
        if self.SIMULATED_PLAYERS is None:
            return not self.is_production and not self.is_test
        return self.SIMULATED_PLAYERS

    @property
    def admin_otp_emails(self) -> set[str]:
        return {e.strip().lower() for e in self.ADMIN_OTP_EMAILS.split(",") if e.strip()}

    @property
    def is_development(self) -> bool:
        """Check if environment is set to development."""
        return self.APP_ENV.lower() == "development"

    @property
    def is_test(self) -> bool:
        """Check if environment is set to test."""
        return self.APP_ENV.lower() == "test"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached instance of application settings."""
    return Settings()
