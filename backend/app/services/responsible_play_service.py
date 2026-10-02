"""Responsible gaming and self-exclusion service."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, ForbiddenException
from app.models.game import GameEntry
from app.models.self_exclusion import SelfExclusion
from app.models.system_setting import SystemSetting
from app.models.wallet import WalletTransaction


class ResponsiblePlayService:
    """Service enforcing responsible play guidelines, daily limits, and self-exclusion."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Self-Exclusion Management
    # ------------------------------------------------------------------

    async def get_active_exclusion(self, user_id: str) -> Optional[SelfExclusion]:
        """Check if user has an ongoing active self-exclusion period."""
        stmt = select(SelfExclusion).where(
            SelfExclusion.user_id == user_id,
            SelfExclusion.is_active == True,  # noqa: E712
        )
        res = await self.session.execute(stmt)
        exclusion = res.scalar_one_or_none()
        if not exclusion:
            return None

        # Check if expired
        now = datetime.now(timezone.utc)
        if exclusion.ends_at.replace(tzinfo=timezone.utc if exclusion.ends_at.tzinfo is None else exclusion.ends_at.tzinfo) < now:
            exclusion.is_active = False
            await self.session.flush()
            return None

        return exclusion

    async def apply_self_exclusion(
        self,
        user_id: str,
        period: Optional[str] = None,
        duration_days: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> SelfExclusion:
        """Apply a cooling-off / self-exclusion period (24h, 7d, permanent, or custom days)."""
        now = datetime.now(timezone.utc)

        if period:
            p_upper = period.upper().strip()
            if p_upper == "24H":
                ends_at = now + timedelta(hours=24)
            elif p_upper == "7D":
                ends_at = now + timedelta(days=7)
            elif p_upper in ("PERMANENT", "FOREVER"):
                ends_at = now + timedelta(days=36500)  # ~100 years
            else:
                raise BadRequestException(f"Invalid period '{period}'. Use '24h', '7d', or 'permanent'.")
        elif duration_days is not None:
            if duration_days < 1:
                raise BadRequestException("Self-exclusion period must be at least 1 day")
            ends_at = now + timedelta(days=duration_days)
        else:
            raise BadRequestException("Either 'period' ('24h', '7d', 'permanent') or 'duration_days' is required.")

        existing = await self.get_active_exclusion(user_id)
        if existing:
            # Can only extend, never shorten
            existing_ends = existing.ends_at.replace(
                tzinfo=timezone.utc if existing.ends_at.tzinfo is None else existing.ends_at.tzinfo
            )
            if ends_at > existing_ends:
                existing.ends_at = ends_at
            if reason:
                existing.reason = reason
            existing.is_active = True
            await self.session.flush()
            return existing

        exclusion = SelfExclusion(
            user_id=user_id,
            starts_at=now,
            ends_at=ends_at,
            reason=reason or f"Player self-exclusion ({period or f'{duration_days} days'})",
            is_active=True,
        )
        self.session.add(exclusion)
        await self.session.flush()
        return exclusion

    # ------------------------------------------------------------------
    # Daily Limits and Session Reminders Config (Key-Value)
    # ------------------------------------------------------------------

    def _setting_key(self, user_id: str) -> str:
        return f"user:{user_id}:responsible_play"

    async def get_user_settings(self, user_id: str) -> Dict[str, Any]:
        """Fetch responsible play limits and reminder configuration."""
        key = self._setting_key(user_id)
        setting = await self.session.get(SystemSetting, key)
        if not setting:
            return {
                "daily_bet_limit_paise": None,
                "daily_loss_limit_paise": None,
                "session_reminder_minutes": 60,
                "session_reminders_enabled": True,
            }
        try:
            return json.loads(setting.value)
        except Exception:
            return {
                "daily_bet_limit_paise": None,
                "daily_loss_limit_paise": None,
                "session_reminder_minutes": 60,
                "session_reminders_enabled": True,
            }

    async def update_user_limits(
        self,
        user_id: str,
        daily_bet_limit_paise: Optional[int] = None,
        daily_loss_limit_paise: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Set daily betting limit and loss limit."""
        if daily_bet_limit_paise is not None and daily_bet_limit_paise < 0:
            raise BadRequestException("Daily bet limit cannot be negative")
        if daily_loss_limit_paise is not None and daily_loss_limit_paise < 0:
            raise BadRequestException("Daily loss limit cannot be negative")

        current = await self.get_user_settings(user_id)
        current["daily_bet_limit_paise"] = daily_bet_limit_paise
        current["daily_loss_limit_paise"] = daily_loss_limit_paise

        key = self._setting_key(user_id)
        setting = await self.session.get(SystemSetting, key)
        if setting:
            setting.value = json.dumps(current)
        else:
            setting = SystemSetting(
                key=key,
                value=json.dumps(current),
                description=f"Responsible play settings for {user_id}",
            )
            self.session.add(setting)
        await self.session.flush()
        return current

    async def update_session_reminders(
        self,
        user_id: str,
        interval_minutes: int,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        """Configure session reminder popups."""
        if interval_minutes not in (15, 30, 45, 60, 90, 120):
            raise BadRequestException("Reminder interval must be one of: 15, 30, 45, 60, 90, 120 minutes")

        current = await self.get_user_settings(user_id)
        current["session_reminder_minutes"] = interval_minutes
        current["session_reminders_enabled"] = enabled

        key = self._setting_key(user_id)
        setting = await self.session.get(SystemSetting, key)
        if setting:
            setting.value = json.dumps(current)
        else:
            setting = SystemSetting(
                key=key,
                value=json.dumps(current),
                description=f"Responsible play settings for {user_id}",
            )
            self.session.add(setting)
        await self.session.flush()
        return current

    # ------------------------------------------------------------------
    # Wager Validation (Enforced in wallet_service.place_bet)
    # ------------------------------------------------------------------

    async def get_today_stats(
        self,
        user_id: str,
        exclude_idempotency_key: Optional[str] = None,
    ) -> Dict[str, int]:
        """Compute today's total wagers and net loss in integer paise."""
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Total bet amount today
        bet_stmt = (
            select(func.coalesce(func.sum(GameEntry.bet_amount), 0))
            .where(
                GameEntry.user_id == user_id,
                GameEntry.created_at >= start_of_day,
                GameEntry.status.notin_(["CANCELLED", "REFUNDED"]),
            )
        )
        if exclude_idempotency_key:
            bet_stmt = bet_stmt.where(
                GameEntry.idempotency_key != exclude_idempotency_key
            )
        res_bet = await self.session.execute(bet_stmt)
        total_wagered = res_bet.scalar_one() or 0

        # Total won amount today
        won_stmt = (
            select(func.coalesce(func.sum(GameEntry.payout_amount), 0))
            .where(
                GameEntry.user_id == user_id,
                GameEntry.created_at >= start_of_day,
                GameEntry.status == "WON",
            )
        )
        if exclude_idempotency_key:
            won_stmt = won_stmt.where(
                GameEntry.idempotency_key != exclude_idempotency_key
            )
        res_won = await self.session.execute(won_stmt)
        total_won = res_won.scalar_one() or 0

        net_loss = max(0, total_wagered - total_won)
        return {
            "total_wagered_today": total_wagered,
            "total_won_today": total_won,
            "net_loss_today": net_loss,
        }

    async def validate_wager_allowed(
        self,
        user_id: str,
        amount_paise: int,
        idempotency_key: Optional[str] = None,
    ) -> None:
        """Validate if user is allowed to place a wager of amount_paise.
        
        Raises ForbiddenException if self-excluded or exceeding limits.
        """
        # 1. Check self-exclusion
        exclusion = await self.get_active_exclusion(user_id)
        if exclusion:
            ends_str = exclusion.ends_at.strftime("%Y-%m-%d %H:%M UTC")
            raise ForbiddenException(
                f"Wagering blocked: Active self-exclusion until {ends_str}"
            )

        # 2. Check daily limits
        settings = await self.get_user_settings(user_id)
        daily_bet_limit = settings.get("daily_bet_limit_paise")
        daily_loss_limit = settings.get("daily_loss_limit_paise")

        if daily_bet_limit is None and daily_loss_limit is None:
            return

        today_stats = await self.get_today_stats(
            user_id,
            exclude_idempotency_key=idempotency_key,
        )

        if daily_bet_limit is not None:
            if today_stats["total_wagered_today"] + amount_paise > daily_bet_limit:
                raise ForbiddenException(
                    f"Wagering blocked: Daily wager limit of {daily_bet_limit} paise exceeded"
                )

        if daily_loss_limit is not None:
            if today_stats["net_loss_today"] + amount_paise > daily_loss_limit:
                raise ForbiddenException(
                    f"Wagering blocked: Daily loss limit of {daily_loss_limit} paise exceeded"
                )
