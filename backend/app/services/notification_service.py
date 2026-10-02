"""Notification service for user alerts and messages."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.redis import get_redis_client
from app.models.notification import Notification
from app.repositories.notification_repo import NotificationRepository
from app.websocket.events import WSEventType, format_ws_event

logger = get_logger("notification_service")


class NotificationService:
    """Service handling player in-app notification alerts with real-time push."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.notif_repo = NotificationRepository(session)

    async def _push_ws_notification(self, user_id: str, notif: Notification) -> None:
        """Push notification to user's real-time WebSocket channel via Redis PubSub."""
        try:
            redis = get_redis_client()
            if redis:
                msg = format_ws_event(
                    event_type=WSEventType.NOTIFICATION.value,
                    data={
                        "id": notif.id,
                        "title": notif.title,
                        "message": notif.message,
                        "type": notif.type,
                        "is_read": notif.is_read,
                        "created_at": notif.created_at.isoformat() if notif.created_at else None,
                    },
                )
                await redis.publish(f"user:{user_id}", msg)
        except Exception as exc:
            logger.debug("Could not push WS notification", user_id=user_id, error=str(exc))

    async def send_notification(
        self,
        user_id: str,
        title: str,
        message: str,
        notification_type: str = "INFO",
    ) -> Notification:
        """Create, flush, and deliver in-app notification to user."""
        notif = await self.notif_repo.create_notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
        )
        await self._push_ws_notification(user_id, notif)
        return notif

    async def send_result_notification(
        self,
        user_id: str,
        game_name: str,
        round_no: int,
        won: bool,
        amount_paise: int,
    ) -> Notification:
        """Deliver round outcome notification (RESULT)."""
        from app.utils.money import format_credits
        credits_str = format_credits(amount_paise)
        if won:
            title = f"{game_name} Win! Round #{round_no}"
            msg = f"Congratulations! You won {credits_str} in {game_name} Round #{round_no}."
        else:
            title = f"{game_name} Round #{round_no} Result"
            msg = f"Round #{round_no} concluded. Better luck next round!"

        return await self.send_notification(
            user_id=user_id,
            title=title,
            message=msg,
            notification_type="RESULT",
        )

    async def send_system_notification(
        self,
        user_id: str,
        title: str,
        message: str,
    ) -> Notification:
        """Deliver platform administrative/maintenance announcement (SYSTEM)."""
        return await self.send_notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type="SYSTEM",
        )

    async def send_account_notification(
        self,
        user_id: str,
        title: str,
        message: str,
    ) -> Notification:
        """Deliver account security, bonus, or wallet adjustment notice (ACCOUNT)."""
        return await self.send_notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type="ACCOUNT",
        )

    async def get_user_notifications(
        self, user_id: str, limit: int = 50, unread_only: bool = False
    ) -> List[Notification]:
        """Fetch notifications list for user."""
        return await self.notif_repo.get_user_notifications(
            user_id=user_id,
            limit=limit,
            unread_only=unread_only,
        )

    async def get_user_notifications_paginated(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
        notification_type: Optional[str] = None,
    ) -> Tuple[List[Notification], int]:
        """Fetch paginated notifications list for user with total count."""
        return await self.notif_repo.get_user_notifications_paginated(
            user_id=user_id,
            limit=limit,
            offset=offset,
            unread_only=unread_only,
            notification_type=notification_type,
        )

    async def get_unread_count(self, user_id: str) -> int:
        """Count unread notifications for user."""
        return await self.notif_repo.get_unread_count(user_id)

    async def mark_as_read(self, notification_id: str, user_id: str) -> bool:
        """Mark single notification as read."""
        return await self.notif_repo.mark_as_read(notification_id, user_id)

    async def mark_all_as_read(self, user_id: str) -> int:
        """Mark all notifications for user as read."""
        return await self.notif_repo.mark_all_as_read(user_id)
