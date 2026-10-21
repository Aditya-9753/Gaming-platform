"""Error handler middleware and exception handler registration."""

from fastapi import FastAPI
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import register_exception_handlers, unhandled_exception_handler


def setup_error_handlers(app: FastAPI) -> None:
    """Register all application domain and unhandled error handlers."""
    register_exception_handlers(app)


class UnhandledErrorMiddleware:
    """Turns an unhandled exception into the standard JSON 500 inside the CORS layer.

    Starlette runs the ``Exception`` handler in its outermost middleware, outside CORS, so a
    crash reached the browser without Access-Control-Allow-Origin and showed up as a network
    error instead of a readable message. Added before ``setup_cors`` so CORS wraps it.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if started:
                raise
            response = await unhandled_exception_handler(Request(scope), exc)
            await response(scope, receive, send)
