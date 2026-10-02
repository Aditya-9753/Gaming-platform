"""Notification API routes for player in-app alerts."""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def list_notifications(
    unread_only: bool = Query(False, description="Filter only unread notifications"),
    notification_type: Optional[str] = Query(None, description="RESULT, SYSTEM, ACCOUNT, INFO"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve paginated in-app notifications for authenticated player."""
    svc = NotificationService(db)
    offset = (page - 1) * page_size
    items, total = await svc.get_user_notifications_paginated(
        user_id=current_user.id,
        limit=page_size,
        offset=offset,
        unread_only=unread_only,
        notification_type=notification_type,
    )
    formatted = [
        {
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "type": n.type,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat(),
        }
        for n in items
    ]
    return {
        "items": formatted,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.get("/unread-count")
async def get_unread_notification_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, int]:
    """Get count of unread notifications for badge counters."""
    svc = NotificationService(db)
    count = await svc.get_unread_count(current_user.id)
    return {"unread_count": count}


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, bool]:
    """Mark a single notification as read."""
    svc = NotificationService(db)
    success = await svc.mark_as_read(notification_id, current_user.id)
    await db.commit()
    return {"success": success}


@router.post("/read-all")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, int]:
    """Mark all unread notifications as read."""
    svc = NotificationService(db)
    count = await svc.mark_all_as_read(current_user.id)
    await db.commit()
    return {"marked_read": count}
