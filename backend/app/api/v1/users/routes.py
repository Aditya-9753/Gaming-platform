"""User profile, settings, and responsible gaming API routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.notification_service import NotificationService
from app.services.responsible_play_service import ResponsiblePlayService
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class UpdateProfileRequest(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[str] = Field(None, min_length=5, max_length=255)


class SelfExclusionRequest(BaseModel):
    duration_days: int = Field(..., ge=1, le=365, description="Duration of cooling-off period in days")
    reason: Optional[str] = Field(None, max_length=255)


@router.get("/me")
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve full user profile, role, and responsible gaming status."""
    resp_svc = ResponsiblePlayService(db)
    exclusion = await resp_svc.get_active_exclusion(current_user.id)

    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role_id": current_user.role_id,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "totp_enabled": current_user.totp_enabled,
        "created_at": current_user.created_at.isoformat(),
        "is_self_excluded": exclusion is not None,
        "self_exclusion_ends_at": exclusion.ends_at.isoformat() if exclusion else None,
    }


@router.put("/me")
async def update_my_profile(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Update user profile attributes (username, email)."""
    svc = UserService(db)
    user = await svc.update_profile(
        user_id=current_user.id,
        username=payload.username,
        email=payload.email,
    )
    await db.commit()
    resp_svc = ResponsiblePlayService(db)
    exclusion = await resp_svc.get_active_exclusion(user.id)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role_id": user.role_id,
        "role": user.role.name if user.role else "USER",
        "is_active": user.is_active,
        "totp_enabled": user.totp_enabled,
        "created_at": user.created_at.isoformat(),
        "is_self_excluded": exclusion is not None,
        "self_exclusion_ends_at": exclusion.ends_at.isoformat() if exclusion else None,
    }


@router.get("/me/history")
async def get_my_history(
    game_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve paginated gameplay and bet history for authenticated user."""
    from app.services.game_service import GameService

    svc = GameService(db)
    offset = (page - 1) * page_size
    entries, total = await svc.get_user_entries(
        user_id=current_user.id,
        game_id=game_id,
        limit=page_size,
        offset=offset,
    )
    items = [
        {
            "entry_id": e.id,
            "round_id": e.round_id,
            "game_id": e.round.game_id if e.round else None,
            "round_no": e.round.round_no if e.round else None,
            "bet_amount": e.bet_amount,
            "payout_amount": e.payout_amount,
            "multiplier": (e.multiplier / 100.0) if e.multiplier else None,
            "status": e.status,
            "selection": (
                {
                    key: value
                    for key, value in (e.selection or {}).items()
                    if key != "mines" or e.status != "PLACED"
                }
                if e.round and e.round.game_id == "mines"
                else e.selection
            ),
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """Update user password."""
    svc = UserService(db)
    await svc.change_password(
        user_id=current_user.id,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    await db.commit()
    return {"message": "Password changed successfully"}


@router.post("/self-exclusion")
async def apply_self_exclusion(
    payload: SelfExclusionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Apply cooling-off self-exclusion to lock wagering for specified days."""
    svc = ResponsiblePlayService(db)
    exclusion = await svc.apply_self_exclusion(
        user_id=current_user.id,
        duration_days=payload.duration_days,
        reason=payload.reason,
    )
    await db.commit()
    return {
        "message": f"Self-exclusion successfully applied for {payload.duration_days} days",
        "ends_at": exclusion.ends_at.isoformat(),
    }


@router.get("/self-exclusion")
async def get_self_exclusion_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Check current active self-exclusion status."""
    svc = ResponsiblePlayService(db)
    exclusion = await svc.get_active_exclusion(current_user.id)
    if not exclusion:
        return {"is_self_excluded": False}

    return {
        "is_self_excluded": True,
        "starts_at": exclusion.starts_at.isoformat(),
        "ends_at": exclusion.ends_at.isoformat(),
        "reason": exclusion.reason,
    }


@router.get("/notifications")
async def list_notifications(
    limit: int = 50,
    unread_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List in-app notifications for user."""
    svc = NotificationService(db)
    notifs = await svc.get_user_notifications(
        user_id=current_user.id,
        limit=min(limit, 100),
        unread_only=unread_only,
    )
    return [
        {
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "type": n.type,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifs
    ]


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, bool]:
    """Mark a notification as read."""
    svc = NotificationService(db)
    success = await svc.mark_as_read(notification_id, current_user.id)
    await db.commit()
    return {"success": success}


@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, int]:
    """Mark all unread notifications as read."""
    svc = NotificationService(db)
    count = await svc.mark_all_as_read(current_user.id)
    await db.commit()
    return {"marked_read": count}
