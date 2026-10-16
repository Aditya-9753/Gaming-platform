"""Indian mobile numbers: one stored form ("+91" + 10 digits) whatever way the player types it."""

from __future__ import annotations

import re
from typing import Optional

_MOBILE = re.compile(r"^[6-9]\d{9}$")


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """'98765 43210', '+91-98765-43210', '09876543210' -> '+919876543210'; None when it is not an Indian mobile number."""
    if raw is None:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return f"+91{digits}" if _MOBILE.match(digits) else None


def looks_like_phone(text: str) -> bool:
    """True when a sign-in identifier is a phone number rather than a username or email."""
    text = text.strip()
    return bool(text) and "@" not in text and not re.search(r"[A-Za-z_]", text) and normalize_phone(text) is not None


def mask_phone(phone: Optional[str]) -> Optional[str]:
    """'+919876543210' -> '+91 98•••••210'."""
    if not phone or len(phone) < 13:
        return phone
    return f"{phone[:3]} {phone[3:5]}•••••{phone[-3:]}"
