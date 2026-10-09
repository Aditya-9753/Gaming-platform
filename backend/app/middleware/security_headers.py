"""Security headers middleware for standard OWASP defense headers."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings


class SecurityHeadersMiddleware:
    """ASGI middleware to append standard security headers to HTTP responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        settings = get_settings()
        self.is_production = settings.is_production

        # The API only serves JSON (and redirects): nothing it returns may run scripts or be framed
        self.headers: list[tuple[bytes, bytes]] = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"x-xss-protection", b"0"),  # legacy filter off; CSP below is the protection
            (b"referrer-policy", b"strict-origin-when-cross-origin"),
            (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"),
            (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
            (b"cross-origin-opener-policy", b"same-origin"),
            (b"cross-origin-resource-policy", b"same-site"),
        ]

        if self.is_production:
            self.headers.append(
                (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                for header_tuple in self.headers:
                    headers.append(header_tuple)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
