"""Asynchronous notification delivery tasks."""

from __future__ import annotations

import asyncio
from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.services.notification_service import NotificationService
from app.workers.celery_app import celery_app

logger = get_logger("worker_notifications")


async def _async_send_notification(
    user_id: str,
    title: str,
    message: str,
    notification_type: str = "INFO",
) -> str:
    async with get_session_factory()() as session:
        notif = await NotificationService(session).send_notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
        )
        await session.commit()
        return notif.id


@celery_app.task(name="app.workers.tasks_notifications.send_user_notification_task")
def send_user_notification_task(
    user_id: str,
    title: str,
    message: str,
    notification_type: str = "INFO",
) -> str:
    """Asynchronously persist and push notification to player."""
    return asyncio.run(_async_send_notification(user_id, title, message, notification_type))
