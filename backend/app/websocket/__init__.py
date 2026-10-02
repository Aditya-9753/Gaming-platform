"""WebSocket package providing connection management and real-time streaming."""

from app.websocket.auth import authenticate_websocket
from app.websocket.events import WSEventType, format_ws_event
from app.websocket.manager import ConnectionManager, ws_manager
from app.websocket.pubsub import RedisPubSubBridge
from app.websocket.routes import router as ws_router

__all__ = [
    "authenticate_websocket",
    "WSEventType",
    "format_ws_event",
    "ConnectionManager",
    "ws_manager",
    "RedisPubSubBridge",
    "ws_router",
]
