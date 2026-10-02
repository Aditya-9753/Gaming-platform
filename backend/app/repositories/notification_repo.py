"""Repository for user notification records."""

from __future__ import annotations

from typing import List, Optional
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


class NotificationRepository:
    """Repository handling Notification database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_notification(
        self,
        user_id: str,
        title: str,
        message: str,
        notification_type: str = "INFO",
    ) -> Notification:
        """Create a new user notification."""
        notif = Notification(
            user_id=user_id,
            title=title,
            message=message,
            type=notification_type,
            is_read=False,
        )
        self.session.add(notif)
        await self.session.flush()
        return notif

    async def get_user_notifications(
        self, user_id: str, limit: int = 50, unread_only: bool = False
    ) -> List[Notification]:
        """Fetch notifications for a user."""
        stmt = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(Notification.is_read == False)  # noqa: E712
        stmt = stmt.order_by(desc(Notification.created_at)).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def mark_as_read(self, notification_id: str, user_id: str) -> bool:
        """Mark single notification as read."""
        stmt = (
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
            .values(is_read=True)
        )
        res = await self.session.execute(stmt)
        await self.session.flush()
        return (res.rowcount or 0) > 0

    async def mark_all_as_read(self, user_id: str) -> int:
        """Mark all notifications for user as read."""
        stmt = (
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
            .values(is_read=True)
        )
        res = await self.session.execute(stmt)
        await self.session.flush()
        return res.rowcount or 0

    async def get_unread_count(self, user_id: str) -> int:
        """Count unread notifications for user."""
        from sqlalchemy import func
        stmt = select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
        res = await self.session.execute(stmt)
        return res.scalar_one() or 0

    async def get_user_notifications_paginated(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
        notification_type: Optional[str] = None,
    ) -> tuple[List[Notification], int]:
        """Fetch paginated notifications for a user with total count."""
        from sqlalchemy import func
        stmt = select(Notification).where(Notification.user_id == user_id)
        count_stmt = select(func.count(Notification.id)).where(Notification.user_id == user_id)

        filters = []
        if unread_only:
            filters.append(Notification.is_read == False)  # noqa: E712
        if notification_type:
            filters.append(Notification.type == notification_type)

        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        stmt = stmt.order_by(desc(Notification.created_at)).limit(limit).offset(offset)
        res = await self.session.execute(stmt)
        return list(res.scalars().all()), total
