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
