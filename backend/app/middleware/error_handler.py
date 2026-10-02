"""Error handler middleware and exception handler registration."""

from fastapi import FastAPI
from app.core.exceptions import register_exception_handlers


def setup_error_handlers(app: FastAPI) -> None:
    """Register all application domain and unhandled error handlers."""
    register_exception_handlers(app)
