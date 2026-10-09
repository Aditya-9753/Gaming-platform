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
    EMAIL_FROM_NAME: str = "RudraWin"
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

    # AES-256-GCM key (64 hex) for payout bank details / UPI ids at rest.
    # Falls back to AUDIT_ENCRYPTION_KEY; required in production once payouts are used.
    PII_ENCRYPTION_KEY: Optional[str] = None
    # Payment provider webhooks: "provider:secret,provider2:secret" (HMAC-SHA256)
    PAYMENT_WEBHOOK_SECRETS: str = ""
    # Optional comma separated source IPs allowed to call the webhook (empty = any)
    PAYMENT_WEBHOOK_IPS: str = ""
    PAYMENT_WEBHOOK_TOLERANCE_SECONDS: int = 300

    # Affiliate / partner platform
    # HMAC-SHA256 secret the operator signs S2S ingest calls with (X-Signature over "<timestamp>.<body>")
    AFFILIATE_INGEST_SECRET: Optional[str] = None
    AFFILIATE_INGEST_TOLERANCE_SECONDS: int = 300
    # Optional comma separated operator IPs allowed to call /ingest (empty = any, signature still required)
    AFFILIATE_INGEST_IPS: str = ""
    # Rudra247 itself reports registrations / deposits / daily revenue to the affiliate ledger
    AFFILIATE_INTERNAL_OPERATOR: bool = True
    # Where the partner portal and the main site live when no tracking domain is configured yet
    # (empty = the first CORS origin, i.e. the deployed frontend)
    AFFILIATE_PUBLIC_BASE_URL: Optional[str] = None
    # Reverse proxies in front of the API (Render: 1). Used to read the real client IP from
    # X-Forwarded-For without trusting the forgeable left-hand entries. 0 = use the socket peer.
    TRUSTED_PROXY_HOPS: int = 1
    # Per-IP ceiling for all API requests per minute (0 = off) and for writes
    GLOBAL_RATE_LIMIT_PER_MINUTE: int = 600
    GLOBAL_WRITE_LIMIT_PER_MINUTE: int = 120

    # Cloudflare Turnstile: with both keys set, sign-in asks for a captcha after 5 failed attempts
    # and locks for 15 minutes after 10 (without keys: lock after 5, as before)
    TURNSTILE_SITE_KEY: Optional[str] = None
    TURNSTILE_SECRET_KEY: Optional[str] = None
    # Reject partner passwords found in public breaches (HaveIBeenPwned range API, k-anonymity)
    AFFILIATE_BREACH_CHECK: bool = True
    # Fetch daily ECB reference FX rates (api.frankfurter.dev) for currency conversion
    AFFILIATE_FX_AUTO_FETCH: bool = True
    # Salt for hashing visitor IPs (required in production)
    AFFILIATE_IP_SALT: Optional[str] = None

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
        # Only HMAC algorithms: never "none", and no asymmetric/symmetric confusion
        if self.JWT_ALGORITHM not in ("HS256", "HS384", "HS512"):
            raise ValueError("JWT_ALGORITHM must be HS256, HS384 or HS512")
        if self.is_production:
            if self.DEBUG:
                raise ValueError("DEBUG must be false in production")
            for name in ("JWT_SECRET", "JWT_REFRESH_SECRET"):
                secret = getattr(self, name)
                if len(secret) < 32 or secret.startswith("replace-with-"):
                    raise ValueError(
                        f"{name} must be a unique secret of at least 32 characters in production"
                    )
            if self.JWT_SECRET == self.JWT_REFRESH_SECRET:
                raise ValueError("JWT_SECRET and JWT_REFRESH_SECRET must be different")
            if any("localhost" in origin or "127.0.0.1" in origin for origin in self.CORS_ORIGINS):
                raise ValueError("Production CORS_ORIGINS must not include localhost")
            if "*" in self.CORS_ORIGINS or any(not origin.startswith("https://") for origin in self.CORS_ORIGINS):
                raise ValueError("Production CORS_ORIGINS must be explicit https:// origins (no wildcard)")
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
    def payment_webhook_secrets(self) -> dict[str, str]:
        pairs = (item.split(":", 1) for item in self.PAYMENT_WEBHOOK_SECRETS.split(",") if ":" in item)
        return {name.strip().lower(): secret.strip() for name, secret in pairs if name.strip() and secret.strip()}

    @property
    def payment_webhook_ips(self) -> set[str]:
        return {ip.strip() for ip in self.PAYMENT_WEBHOOK_IPS.split(",") if ip.strip()}

    @property
    def affiliate_public_base_url(self) -> str:
        """Main site URL for partner links / emails: explicit setting, else the frontend's CORS origin."""
        if self.AFFILIATE_PUBLIC_BASE_URL:
            return self.AFFILIATE_PUBLIC_BASE_URL.rstrip("/")
        origins = [o for o in self.CORS_ORIGINS if o.startswith("http")]
        return (origins[0] if origins else "http://localhost:5173").rstrip("/")

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
