"""Per-IP ceiling for every API request (on top of the stricter per-endpoint limits).

Stops scraping and brute force on endpoints without their own limit. Health checks and the
tracking redirect (which has its own bot logic) are exempt. Uses Redis, falling back to
memory, like the rest of the rate limiting.
"""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.rate_limit import check_rate_limit

_EXEMPT_PREFIXES = ("/health", "/api/v1/health", "/r/", "/ws")


class GlobalRateLimitMiddleware:
    def __init__(self, app: ASGIApp, per_minute: int, writes_per_minute: int) -> None:
        self.app = app
        self.per_minute = per_minute
        self.writes_per_minute = writes_per_minute

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.per_minute <= 0 or scope["path"].startswith(_EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return
        from app.core.client_ip import from_headers

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        ip = from_headers(headers, (scope.get("client") or ("unknown", 0))[0])
        allowed = await check_rate_limit(f"rl:global:{ip}", self.per_minute, 60)
        if allowed and scope["method"] in ("POST", "PUT", "PATCH", "DELETE"):
            allowed = await check_rate_limit(f"rl:global-w:{ip}", self.writes_per_minute, 60)
        if not allowed:
            response = JSONResponse(
                {"success": False, "error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many requests, slow down", "details": None}},
                status_code=429,
                headers={"Retry-After": "60"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
