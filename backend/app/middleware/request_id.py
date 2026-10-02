"""Request ID tracking middleware.

Extracts incoming X-Request-ID or generates a new UUID4, binding it
to contextvars and the HTTP response headers.
"""

from uuid import uuid4
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import set_request_id

REQUEST_ID_HEADER = "x-request-id"


class RequestIdMiddleware:
    """ASGI middleware for setting and propagating unique request IDs."""

    def __init__(self, app: ASGIApp, header_name: str = REQUEST_ID_HEADER) -> None:
        self.app = app
        self.header_name = header_name.lower()
        self.header_name_bytes = self.header_name.encode("latin1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract existing X-Request-ID or create new one
        request_id: str = ""
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name.lower() == self.header_name_bytes:
                request_id = raw_value.decode("latin1").strip()
                break

        if not request_id:
            request_id = uuid4().hex

        # Bind to async context for logging
        set_request_id(request_id)

        # Store in scope state
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((self.header_name_bytes, request_id.encode("latin1")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_request_id)
