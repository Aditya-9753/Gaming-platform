"""CSRF protection for cookie-authenticated requests.

API calls authenticate with a Bearer header, which a foreign site cannot attach, so they are
not CSRF-able. The cookies this API sets (refresh_token on /api/v1/auth, aff_click / aff_vid
for tracking) *are* sent automatically by browsers, so every state-changing request that
carries cookies must come from an allowed origin:

* Origin header present  -> must be in CORS_ORIGINS (or this API's own origin);
* no Origin, Referer set -> the Referer's origin must be allowed;
* neither (curl, server-to-server, old clients) -> allowed: browsers always send Origin on
  cross-site POST / PUT / PATCH / DELETE, so the request did not come from a foreign page.
"""

from __future__ import annotations

from typing import Iterable, Optional
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _origin_of(url: str) -> Optional[str]:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


class CSRFOriginMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: Iterable[str]) -> None:
        self.app = app
        self.allowed = {o.rstrip("/").lower() for o in allowed_origins if o and o != "*"}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in _UNSAFE:
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if "cookie" not in headers:
            await self.app(scope, receive, send)
            return
        own = f"{scope.get('scheme', 'http')}://{headers.get('host', '')}".lower()
        origin = headers.get("origin")
        source = origin if origin else (_origin_of(headers["referer"]) if headers.get("referer") else None)
        if origin == "null" or (source is not None and source.rstrip("/").lower() not in self.allowed | {own}):
            response = JSONResponse(
                {"success": False, "error": {"code": "CSRF_REJECTED", "message": "Cross-site request blocked", "details": None}},
                status_code=403,
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
