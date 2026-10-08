"""Global affiliate settings (PRD ``app_settings``), stored in ``system_settings`` as ``aff.<key>``.

Values are JSON so lists (languages) and maps (fallback FX rates) fit the same
key/value table the platform already uses.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any, Callable, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.models.system_setting import SystemSetting

_PREFIX = "aff."


def _num(lo: float, hi: float) -> Callable[[Any], Any]:
    def check(value: Any) -> Any:
        try:
            num = Decimal(str(value))
        except Exception as exc:
            raise BadRequestException("must be a number") from exc
        if num < Decimal(str(lo)) or num > Decimal(str(hi)):
            raise BadRequestException(f"must be between {lo} and {hi}")
        return str(num)
    return check


def _int(lo: int, hi: int) -> Callable[[Any], Any]:
    def check(value: Any) -> int:
        try:
            num = int(value)
        except (TypeError, ValueError) as exc:
            raise BadRequestException("must be a whole number") from exc
        if num < lo or num > hi:
            raise BadRequestException(f"must be between {lo} and {hi}")
        return num
    return check


def _choice(*options: str) -> Callable[[Any], str]:
    def check(value: Any) -> str:
        text = str(value).upper()
        if text not in options:
            raise BadRequestException(f"must be one of {', '.join(options)}")
        return text
    return check


def _text(max_len: int = 500) -> Callable[[Any], str]:
    def check(value: Any) -> str:
        text = str(value or "").strip()
        if len(text) > max_len:
            raise BadRequestException(f"must be at most {max_len} characters")
        return text
    return check


def _bool(value: Any) -> bool:
    return value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes", "on")


def _languages(value: Any) -> list:
    items = value if isinstance(value, list) else str(value).split(",")
    langs = [str(v).strip().lower() for v in items if str(v).strip()]
    if not langs or any(len(code) > 8 or not code.isalpha() for code in langs):
        raise BadRequestException("must be a list of language codes, e.g. en, hi")
    return langs


def _fx_map(value: Any) -> Dict[str, str]:
    if isinstance(value, str):
        value = json.loads(value or "{}")
    if not isinstance(value, dict):
        raise BadRequestException("must be an object like {\"INR\": \"0.012\"}")
    out = {}
    for cur, rate in value.items():
        cur = str(cur).upper()
        if len(cur) != 3:
            raise BadRequestException(f"bad currency {cur}")
        dec = Decimal(str(rate))
        if dec <= 0:
            raise BadRequestException(f"rate for {cur} must be positive")
        out[cur] = str(dec)
    return out


# key -> (default, validator, description)
SCHEMA: Dict[str, Tuple[Any, Callable[[Any], Any], str]] = {
    "min_payout": ("20", _num(1, 100000), "Smallest withdrawal a partner can request (USD)"),
    "withdrawal_fee": ("0", _num(0, 1000), "Flat fee taken from every partner withdrawal (USD)"),
    "method_cooldown_hours": (24, _int(0, 720), "Hours a new or changed payout method waits before its first payout"),
    "default_hold_days": (14, _int(0, 180), "CPA fraud hold for new deals (days)"),
    "cookie_days": (30, _int(1, 365), "Lifetime of the aff_click tracking cookie (days)"),
    "attribution_window_days": (30, _int(1, 365), "Last click within this many days wins the registration"),
    "settlement_period_type": ("WEEKLY", _choice("WEEKLY", "MONTHLY"), "Length of settlement periods"),
    "default_subpartner_rate": ("0.05", _num(0, 1), "Share of a subpartner's positive commission paid to the master partner"),
    "subpartner_depth": (1, _int(0, 1), "Subpartner levels (0 = off, 1 = direct subpartners)"),
    "default_plan_id": (0, _int(0, 10**12), "Commission plan given to self sign-ups (0 = first active plan)"),
    "auto_approve_signups": (False, _bool, "Activate self sign-ups without admin approval"),
    "default_destination_url": ("", _text(), "Where tracking links send players (empty = the main site's sign-up page)"),
    "blocked_geo_url": ("", _text(), "Where players from a blocked country are sent (empty = main site)"),
    "bot_clicks_per_minute": (30, _int(1, 10000), "Clicks per IP per minute after which further clicks count as bots"),
    "unique_click_window_hours": (24, _int(1, 720), "A repeat click from the same IP on the same link within this window is not unique"),
    "app_android_url": ("", _text(), "Android app download link shown in the partner portal header"),
    "app_ios_url": ("", _text(), "iOS app download link shown in the partner portal header"),
    "languages": (["en", "hi"], _languages, "Partner portal languages"),
    "fallback_fx_rates": ({}, _fx_map, "Manual rate to USD for currencies the ECB does not publish (daily ECB rates are fetched automatically)"),
    "terms_required": (True, _bool, "Partners must accept the latest terms before using the portal"),
    "auto_close_periods": (False, _bool, "Close ended settlement periods automatically (off = finance closes them)"),
}

PUBLIC_KEYS = ("app_android_url", "app_ios_url", "languages", "min_payout", "cookie_days")

_cache: Dict[str, Any] = {}
_cache_at = 0.0
_TTL = 5.0


async def get_all(session: AsyncSession, fresh: bool = False) -> Dict[str, Any]:
    global _cache, _cache_at
    if not fresh and _cache and time.monotonic() - _cache_at < _TTL:
        return dict(_cache)
    keys = [_PREFIX + k for k in SCHEMA]
    rows = (await session.execute(select(SystemSetting).where(SystemSetting.key.in_(keys)))).scalars().all()
    stored = {row.key[len(_PREFIX):]: row.value for row in rows}
    values: Dict[str, Any] = {}
    for key, (default, validator, _desc) in SCHEMA.items():
        if key in stored:
            try:
                values[key] = validator(json.loads(stored[key]))
                continue
            except Exception:
                pass
        values[key] = default
    _cache, _cache_at = values, time.monotonic()
    return dict(values)


async def get(session: AsyncSession, key: str) -> Any:
    return (await get_all(session))[key]


async def get_decimal(session: AsyncSession, key: str) -> Decimal:
    return Decimal(str(await get(session, key)))


def describe() -> Dict[str, str]:
    return {key: desc for key, (_d, _v, desc) in SCHEMA.items()}


async def update(session: AsyncSession, changes: Dict[str, Any], actor_id: Optional[str]) -> Dict[str, Any]:
    global _cache_at
    unknown = set(changes) - set(SCHEMA)
    if unknown:
        raise BadRequestException(f"Unknown setting(s): {', '.join(sorted(unknown))}")
    for key, raw in changes.items():
        try:
            value = SCHEMA[key][1](raw)
        except BadRequestException as exc:
            raise BadRequestException(f"{key} {exc.message}") from exc
        row = await session.get(SystemSetting, _PREFIX + key)
        stored = json.dumps(value)
        if row is None:
            session.add(SystemSetting(key=_PREFIX + key, value=stored, description=SCHEMA[key][2][:255], updated_by_id=actor_id))
        else:
            row.value = stored
            row.updated_by_id = actor_id
    await session.flush()
    _cache_at = 0.0
    return await get_all(session, fresh=True)


def reset_cache() -> None:
    global _cache_at
    _cache_at = 0.0
