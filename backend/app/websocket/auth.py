"""WebSocket authentication with short-lived tickets and JWT fallback."""

from __future__ import annotations

import secrets
from typing import Optional
from fastapi import WebSocket, status
from redis.asyncio import Redis

from app.core.logging import get_logger
from app.core.redis import get_redis_client
from app.core.security import decode_access_token

logger = get_logger("ws_auth")


async def create_ws_ticket(redis: Redis, user_id: str, ttl_seconds: int = 60) -> str:
    """Generate a single-use, short-lived ticket token for secure WebSocket authentication."""
    ticket = secrets.token_urlsafe(32)
    key = f"ws:ticket:{ticket}"
    await redis.set(key, user_id, ex=ttl_seconds)
    return ticket


async def validate_and_consume_ticket(redis: Redis, ticket: str) -> Optional[str]:
    """Validate ticket and immediately delete it (single-use semantics)."""
    key = f"ws:ticket:{ticket}"
    user_id = await redis.get(key)
    if user_id:
        await redis.delete(key)
        if isinstance(user_id, bytes):
            return user_id.decode("utf-8")
        return str(user_id)
    return None


async def authenticate_websocket(
    websocket: WebSocket,
    required: bool = True,
    redis: Optional[Redis] = None,
) -> Optional[str]:
    """Authenticate WebSocket connection using single-use ticket or JWT.

    Priority:
    1. Query param ``?ticket=...`` (consumed from Redis)
    2. Query param ``?token=...`` (JWT)
    3. ``Authorization: Bearer ...`` header
    4. Cookie ``access_token``
    """
    # 1. Ticket-based authentication
    ticket = websocket.query_params.get("ticket")
    if ticket:
        r = redis or get_redis_client()
        try:
            user_id = await validate_and_consume_ticket(r, ticket)
            if user_id:
                return user_id
        except Exception as exc:
            logger.warning("Ticket validation error", error=str(exc))

    # 2. Token-based authentication (fallback)
    token: Optional[str] = None
    if "token" in websocket.query_params:
        token = websocket.query_params["token"]
    elif "authorization" in websocket.headers:
        auth_header = websocket.headers["authorization"]
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    elif "access_token" in websocket.cookies:
        token = websocket.cookies["access_token"]

    if token:
        try:
            payload = decode_access_token(token)
            uid = payload.get("sub")
            if uid:
                return str(uid)
        except Exception as exc:
            logger.warning("JWT WS authentication failed", error=str(exc))

    if required:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    return None
