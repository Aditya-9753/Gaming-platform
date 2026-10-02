"""Responsible Gaming API endpoints for daily limits, session reminders, and self-exclusion."""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.responsible_play_service import ResponsiblePlayService

router = APIRouter(prefix="/responsible-play", tags=["Responsible Play"])


class UpdateLimitsRequest(BaseModel):
    daily_bet_limit_paise: Optional[int] = Field(
        None, ge=0, description="Maximum total bets allowed in a 24h day (paise), null to remove"
    )
    daily_loss_limit_paise: Optional[int] = Field(
        None, ge=0, description="Maximum net loss allowed in a 24h day (paise), null to remove"
    )


class SessionReminderRequest(BaseModel):
    interval_minutes: int = Field(
        ..., description="Reminder interval in minutes (15, 30, 45, 60, 90, 120)"
    )
    enabled: bool = Field(True, description="Enable or disable session reminder popups")


class SelfExclusionRequest(BaseModel):
    period: Optional[str] = Field(
        None, description="'24h', '7d', or 'permanent'"
    )
    duration_days: Optional[int] = Field(
        None, ge=1, le=36500, description="Custom exclusion duration in days"
    )
    reason: Optional[str] = Field(None, max_length=255)


@router.get("")
async def get_responsible_play_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve full responsible gaming settings, limits, and active self-exclusion status."""
    svc = ResponsiblePlayService(db)
    exclusion = await svc.get_active_exclusion(current_user.id)
    settings = await svc.get_user_settings(current_user.id)
    today_stats = await svc.get_today_stats(current_user.id)

    return {
        "user_id": current_user.id,
        "is_self_excluded": exclusion is not None,
        "self_exclusion": {
            "starts_at": exclusion.starts_at.isoformat() if exclusion else None,
            "ends_at": exclusion.ends_at.isoformat() if exclusion else None,
            "reason": exclusion.reason if exclusion else None,
        } if exclusion else None,
        "limits": {
            "daily_bet_limit_paise": settings.get("daily_bet_limit_paise"),
            "daily_loss_limit_paise": settings.get("daily_loss_limit_paise"),
        },
        "session_reminders": {
            "interval_minutes": settings.get("session_reminder_minutes", 60),
            "enabled": settings.get("session_reminders_enabled", True),
        },
        "today_activity": today_stats,
    }


@router.post("/limits")
async def update_daily_limits(
    payload: UpdateLimitsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Set or update user daily wagering and loss limits in paise."""
    svc = ResponsiblePlayService(db)
    settings = await svc.update_user_limits(
        user_id=current_user.id,
        daily_bet_limit_paise=payload.daily_bet_limit_paise,
        daily_loss_limit_paise=payload.daily_loss_limit_paise,
    )
    await db.commit()
    return {
        "message": "Responsible play limits updated successfully",
        "limits": {
            "daily_bet_limit_paise": settings.get("daily_bet_limit_paise"),
            "daily_loss_limit_paise": settings.get("daily_loss_limit_paise"),
        },
    }


@router.post("/session-reminders")
async def update_session_reminders(
    payload: SessionReminderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Configure in-app reality check / session reminder frequency."""
    svc = ResponsiblePlayService(db)
    settings = await svc.update_session_reminders(
        user_id=current_user.id,
        interval_minutes=payload.interval_minutes,
        enabled=payload.enabled,
    )
    await db.commit()
    return {
        "message": "Session reminder preferences saved",
        "session_reminders": {
            "interval_minutes": settings.get("session_reminder_minutes"),
            "enabled": settings.get("session_reminders_enabled"),
        },
    }


@router.post("/self-exclusion")
async def apply_self_exclusion(
    payload: SelfExclusionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Apply self-exclusion (24h, 7d, permanent, or custom duration) blocking all wagering."""
    svc = ResponsiblePlayService(db)
    exclusion = await svc.apply_self_exclusion(
        user_id=current_user.id,
        period=payload.period,
        duration_days=payload.duration_days,
        reason=payload.reason,
    )
    await db.commit()
    return {
        "message": "Self-exclusion successfully activated. Wagering is blocked.",
        "starts_at": exclusion.starts_at.isoformat(),
        "ends_at": exclusion.ends_at.isoformat(),
        "reason": exclusion.reason,
        "is_active": exclusion.is_active,
    }


@router.get("/status")
async def get_responsible_play_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get active wagering allowance and self-exclusion enforcement status."""
    svc = ResponsiblePlayService(db)
    exclusion = await svc.get_active_exclusion(current_user.id)
    settings = await svc.get_user_settings(current_user.id)
    today = await svc.get_today_stats(current_user.id)

    daily_bet_limit = settings.get("daily_bet_limit_paise")
    daily_loss_limit = settings.get("daily_loss_limit_paise")

    remaining_bet = None
    if daily_bet_limit is not None:
        remaining_bet = max(0, daily_bet_limit - today["total_wagered_today"])

    remaining_loss = None
    if daily_loss_limit is not None:
        remaining_loss = max(0, daily_loss_limit - today["net_loss_today"])

    return {
        "is_self_excluded": exclusion is not None,
        "self_exclusion_ends_at": exclusion.ends_at.isoformat() if exclusion else None,
        "daily_bet_limit_paise": daily_bet_limit,
        "daily_loss_limit_paise": daily_loss_limit,
        "wagered_today_paise": today["total_wagered_today"],
        "net_loss_today_paise": today["net_loss_today"],
        "remaining_bet_allowance_paise": remaining_bet,
        "remaining_loss_allowance_paise": remaining_loss,
    }
