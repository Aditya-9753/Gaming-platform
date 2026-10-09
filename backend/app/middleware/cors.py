"""CORS middleware configuration: explicit origins, methods and headers only."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
ALLOWED_HEADERS = [
    "Authorization", "Content-Type", "Accept", "Accept-Language", "Idempotency-Key", "X-Request-ID",
    "X-Step-Up-Token", "X-Requested-With",
]


def setup_cors(app: FastAPI) -> None:
    """Configure Cross-Origin Resource Sharing (CORS) on the application."""
    settings = get_settings()

    origins = settings.CORS_ORIGINS
    if isinstance(origins, str):
        origins = [origins]
    origins = [o for o in origins if o != "*"]  # credentials + wildcard is never allowed

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
        expose_headers=["X-Request-ID", "Retry-After"],
        max_age=600,
    )
