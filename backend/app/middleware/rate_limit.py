"""Rate limit middleware helpers."""

from typing import Callable
from fastapi import Request
from app.core.exceptions import RateLimitException
from app.core.rate_limit import check_rate_limit


def rate_limit_dependency(key_prefix: str, max_requests: int, window_seconds: int) -> Callable:
    """Create a FastAPI dependency that enforces rate limits per client IP."""

    async def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"rate_limit:{key_prefix}:{client_ip}"
        allowed = await check_rate_limit(key, max_requests, window_seconds)
        if not allowed:
            raise RateLimitException(
                message=f"Too many requests for {key_prefix}. Please wait before retrying."
            )

    return dependency
