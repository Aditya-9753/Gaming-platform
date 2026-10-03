"""Platform-wide settings (branding, maintenance mode, credit amounts).

Stored as key/value rows in ``system_settings``; read through a short
in-process cache so hot paths (every bet checks maintenance) stay cheap.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, ServiceUnavailableException
from app.models.system_setting import SystemSetting

# key -> (type, default, description)
SETTINGS_SCHEMA: Dict[str, tuple] = {
    "platform_name": (str, "Rudra247", "Brand name shown across the site"),
    "platform_logo_url": (str, "", "Logo image URL (empty = default flame logo)"),
    "maintenance_mode": (bool, False, "Block new bets for everyone except staff"),
    "maintenance_message": (str, "We are upgrading the platform. Betting resumes shortly.", "Banner text during maintenance"),
    "signup_bonus_paise": (int, 10000, "Virtual credits given at sign-up (paise)"),
    "daily_claim_amount_paise": (int, 1000, "Daily bonus amount (paise)"),
    # Payments
    "payments_enabled": (bool, True, "Accept new deposits and withdrawal requests"),
    "deposit_min_paise": (int, 10000, "Smallest deposit (paise)"),
    "deposit_max_paise": (int, 10000000, "Largest single deposit (paise)"),
    "deposit_expiry_minutes": (int, 30, "Minutes a deposit QR stays payable"),
    "deposit_unique_paise": (bool, False, "Add a few random paise to each deposit so statement lines match automatically (off = exact amount)"),
    "manual_deposit_super_threshold_paise": (int, 2500000, "Manual deposit confirmations above this need the super admin (paise)"),
    "withdrawal_min_paise": (int, 20000, "Smallest withdrawal (paise)"),
    "withdrawal_max_paise": (int, 5000000, "Largest single withdrawal (paise)"),
    "withdrawal_daily_count": (int, 3, "Withdrawal requests allowed per player per day"),
    "withdrawal_daily_amount_paise": (int, 10000000, "Withdrawal total allowed per player per day (paise)"),
    "withdrawal_high_value_paise": (int, 2500000, "Withdrawals at or above this need maker-checker: another admin initiates first (paise)"),
    "withdrawal_requires_deposit": (bool, True, "Only players with a successful deposit can withdraw"),
    "withdrawal_turnover_pct": (int, 100, "Players must wager this % of their deposits before withdrawing"),
    "beneficiary_cooling_hours": (int, 24, "Hours before a new payout account (or changed PIN) can be used"),
}
# daily_claim_amount_paise is public so the claim card shows the amount the server really credits
PUBLIC_KEYS = ("platform_name", "platform_logo_url", "maintenance_mode", "maintenance_message", "daily_claim_amount_paise", "payments_enabled")

_CACHE_TTL = 5.0
_cache: Dict[str, Any] = {}
_cache_at = 0.0


def _coerce(key: str, raw: Any) -> Any:
    kind, _default, _desc = SETTINGS_SCHEMA[key]
    if kind is bool:
        return raw if isinstance(raw, bool) else str(raw).strip().lower() in ("1", "true", "yes", "on")
    if kind is int:
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise BadRequestException(f"{key} must be a whole number") from exc
        if value < 0 or value > 100_000_000:
            raise BadRequestException(f"{key} is out of range")
        return value
    value = str(raw).strip()
    if len(value) > 500:
        raise BadRequestException(f"{key} is too long")
    if key == "platform_name" and not 2 <= len(value) <= 40:
        raise BadRequestException("Platform name must be 2-40 characters")
    if key == "platform_logo_url" and value and not value.startswith(("https://", "http://", "/")):
        raise BadRequestException("Logo URL must start with https://, http:// or /")
    return value


async def get_all(session: AsyncSession, fresh: bool = False) -> Dict[str, Any]:
    global _cache, _cache_at
    if not fresh and _cache and time.monotonic() - _cache_at < _CACHE_TTL:
        return dict(_cache)
    rows = (await session.execute(select(SystemSetting).where(SystemSetting.key.in_(list(SETTINGS_SCHEMA))))).scalars().all()
    stored = {row.key: row.value for row in rows}
    values = {key: _coerce(key, stored[key]) if key in stored else default for key, (_k, default, _d) in SETTINGS_SCHEMA.items()}
    _cache, _cache_at = values, time.monotonic()
    return dict(values)


async def update(session: AsyncSession, changes: Dict[str, Any], actor_id: Optional[str]) -> Dict[str, Any]:
    global _cache_at
    unknown = set(changes) - set(SETTINGS_SCHEMA)
    if unknown:
        raise BadRequestException(f"Unknown setting(s): {', '.join(sorted(unknown))}")
    for key, raw in changes.items():
        value = _coerce(key, raw)
        stored = "true" if value is True else "false" if value is False else str(value)
        row = await session.get(SystemSetting, key)
        if row is None:
            session.add(SystemSetting(key=key, value=stored, description=SETTINGS_SCHEMA[key][2], updated_by_id=actor_id))
        else:
            row.value = stored
            row.updated_by_id = actor_id
    await session.flush()
    _cache_at = 0.0  # invalidate
    return await get_all(session, fresh=True)


async def ensure_betting_open(session: AsyncSession, role: Optional[str] = None) -> None:
    """Raise while maintenance mode is on (staff may still test)."""
    settings = await get_all(session)
    if settings["maintenance_mode"] and (role or "").upper() not in ("SUPERADMIN", "ADMIN"):
        raise ServiceUnavailableException(settings["maintenance_message"] or "Platform is under maintenance")
