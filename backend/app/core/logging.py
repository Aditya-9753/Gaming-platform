"""Structured JSON logging with request ID tracking."""

import logging
import sys
from contextvars import ContextVar
from typing import Any, Optional
import structlog
from app.core.config import get_settings

# Context variable for tracking request ID across async tasks
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def set_request_id(req_id: str) -> None:
    """Store the active request ID in current async context."""
    request_id_ctx.set(req_id)


def get_request_id() -> Optional[str]:
    """Retrieve the active request ID from current async context."""
    return request_id_ctx.get()


def _add_request_id(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Structlog processor to inject request_id if available."""
    req_id = get_request_id()
    if req_id is not None:
        event_dict["request_id"] = req_id
    return event_dict


_SENSITIVE_KEYS = {
    "password", "new_password", "current_password", "password_hash", "token", "access_token", "refresh_token",
    "raw_token", "reset_token", "verify_token", "secret", "totp_secret", "api_key", "authorization", "cookie",
    "code", "otp", "otp_code", "totp_code", "pin", "transaction_pin", "captcha_token", "signature", "x-signature",
    "account_number", "account_identifier", "upi_id", "ifsc", "card", "cvv", "body", "payload",
}
_TOKEN_PATTERNS = None


def _redact_value(value: Any) -> Any:
    global _TOKEN_PATTERNS
    if not isinstance(value, str):
        return value
    if _TOKEN_PATTERNS is None:
        import re

        _TOKEN_PATTERNS = [
            (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[jwt]"),  # JWTs
            (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{12,}"), r"\1[token]"),
            (re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)=([^&\s]+)"), r"\1=[redacted]"),
        ]
    for pattern, repl in _TOKEN_PATTERNS:
        value = pattern.sub(repl, value)
    return value


def _redact(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Structlog processor: never let secrets / payout details reach the logs."""
    for key in list(event_dict):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = "[redacted]"
        else:
            event_dict[key] = _redact_value(event_dict[key])
    return event_dict


def setup_logging() -> None:
    """Configure structured JSON logging for the application."""
    settings = get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Intercept standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _add_request_id,
        _redact,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: Optional[str] = None) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)
