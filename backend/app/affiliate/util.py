"""Small helpers: money rounding, codes, click ids, hashing, masking, request info."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Optional, Tuple

from fastapi import Request

from app.affiliate.constants import MONEY_Q
from app.core.config import get_settings
from app.core.exceptions import BadRequestException

# Base32 without the look-alikes 0/O and 1/I (PRD §5)
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DEV_IP_SALT = "rudra247-affiliate-dev-ip-salt"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite returns naive datetimes; treat them as UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def money(value: Any) -> Decimal:
    """Parse to a 4-dp Decimal (never via float)."""
    if isinstance(value, Decimal):
        dec = value
    else:
        try:
            dec = Decimal(str(value).strip())
        except (InvalidOperation, AttributeError) as exc:
            raise BadRequestException(f"Invalid amount: {value!r}") from exc
    if not dec.is_finite():
        raise BadRequestException("Amount must be a finite number")
    return dec.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def money_out(value: Optional[Decimal]) -> str:
    """Serialize money for JSON as a 2-dp string ("-218.31")."""
    return str(money(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def rate(value: Any) -> Decimal:
    dec = money(value).quantize(Decimal("0.0001"))
    if dec < 0 or dec > 1:
        raise BadRequestException("Rates are fractions between 0 and 1 (0.5 = 50%)")
    return dec


def random_code(length: int = 8) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def new_click_id(now: Optional[datetime] = None) -> str:
    """26-char ULID: 48-bit ms timestamp + 80 random bits, Crockford base32 (sortable)."""
    ts = int((now or utcnow()).timestamp() * 1000)
    value = (ts << 80) | secrets.randbits(80)
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def click_time(click_id: str) -> Optional[datetime]:
    """Decode the timestamp embedded in a click id (lets us hit the right partition)."""
    if not click_id or len(click_id) != 26:
        return None
    value = 0
    for ch in click_id.upper():
        idx = _CROCKFORD.find(ch)
        if idx < 0:
            return None
        value = (value << 5) | idx
    ms = value >> 80
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _ip_salt() -> str:
    settings = get_settings()
    if settings.AFFILIATE_IP_SALT:
        return settings.AFFILIATE_IP_SALT
    if settings.is_production:
        # Stable secret derived from the JWT secret (production enforces >= 32 chars) so a click
        # never fails just because the dedicated salt was not configured
        return hmac.new(settings.JWT_SECRET.encode(), b"affiliate-ip-salt", hashlib.sha256).hexdigest()
    return _DEV_IP_SALT


def hash_ip(ip: Optional[str]) -> Optional[str]:
    if not ip:
        return None
    return hmac.new(_ip_salt().encode(), ip.encode(), hashlib.sha256).hexdigest()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def client_ip(request: Request) -> Optional[str]:
    from app.core.client_ip import of_request

    return of_request(request)


def request_country(request: Request) -> Optional[str]:
    """Country from the CDN header (Cloudflare / Vercel). None when unknown."""
    for header in ("cf-ipcountry", "x-vercel-ip-country", "x-country-code"):
        value = (request.headers.get(header) or "").strip().upper()
        if len(value) == 2 and value.isalpha() and value != "XX":
            return value
    return None


def mask_identifier(value: str) -> str:
    """ru****@gmail.com / TQ7x****9kLm / ****4321."""
    value = value.strip()
    if "@" in value:
        name, _, domain = value.partition("@")
        return f"{name[:2]}****@{domain}"
    if len(value) <= 6:
        return "****" + value[-2:]
    if len(value) >= 20:
        return f"{value[:4]}****{value[-4:]}"
    return "****" + value[-4:]


_BOT_RE = re.compile(
    r"bot|crawl|spider|slurp|headless|phantom|curl|wget|python-requests|httpclient|go-http|java/|"
    r"facebookexternalhit|preview|monitor|scanner|lighthouse|pingdom|uptime",
    re.IGNORECASE,
)


def is_bot_agent(user_agent: Optional[str]) -> bool:
    return not user_agent or bool(_BOT_RE.search(user_agent))


def parse_user_agent(ua: Optional[str]) -> Tuple[str, str, str]:
    """(device_type, browser, os) — coarse, dependency-free."""
    ua = ua or ""
    low = ua.lower()
    if "ipad" in low or "tablet" in low:
        device = "tablet"
    elif "mobi" in low or "android" in low or "iphone" in low:
        device = "mobile"
    elif not ua:
        device = "unknown"
    else:
        device = "desktop"
    if "edg/" in low:
        browser = "Edge"
    elif "opr/" in low or "opera" in low:
        browser = "Opera"
    elif "samsungbrowser" in low:
        browser = "Samsung"
    elif "chrome/" in low and "chromium" not in low:
        browser = "Chrome"
    elif "firefox/" in low:
        browser = "Firefox"
    elif "safari/" in low:
        browser = "Safari"
    else:
        browser = "Other"
    if "android" in low:
        os_name = "Android"
    elif "iphone" in low or "ipad" in low or "ios" in low:
        os_name = "iOS"
    elif "windows" in low:
        os_name = "Windows"
    elif "mac os" in low or "macintosh" in low:
        os_name = "macOS"
    elif "linux" in low:
        os_name = "Linux"
    else:
        os_name = "Other"
    return device, browser, os_name


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def month_bounds(day: date) -> Tuple[date, date]:
    start = day.replace(day=1)
    nxt = (start + timedelta(days=32)).replace(day=1)
    return start, nxt - timedelta(days=1)

