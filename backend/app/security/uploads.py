"""Validation of user-supplied files (images sent as data URLs, CSV text).

A data URL is accepted only when the base64 decodes strictly, the decoded bytes start with
the signature of the declared format (PNG / JPEG / WebP / GIF) and the size is within the limit.
SVG is never accepted (it can carry scripts).
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import Optional

from app.core.exceptions import BadRequestException

_DATA_URL = re.compile(r"^data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=\s]+)$")
_SIGNATURES = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpeg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"),
}

DEFAULT_MAX_IMAGE_BYTES = 2 * 1024 * 1024


def _matches(kind: str, raw: bytes) -> bool:
    if kind == "webp":
        return len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"
    return any(raw.startswith(sig) for sig in _SIGNATURES[kind])


def validate_image_data_url(value: Optional[str], max_bytes: int = DEFAULT_MAX_IMAGE_BYTES, label: str = "Image") -> Optional[str]:
    """Return the cleaned data URL or raise BadRequestException."""
    if not value:
        return None
    value = value.strip()
    match = _DATA_URL.match(value)
    if not match:
        raise BadRequestException(f"{label} must be a PNG, JPEG, WebP or GIF image")
    kind, body = match.group(1), re.sub(r"\s+", "", match.group(2))
    if len(body) > (max_bytes * 4) // 3 + 4:
        raise BadRequestException(f"{label} is larger than {max_bytes // 1024} KB")
    try:
        raw = base64.b64decode(body, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BadRequestException(f"{label} is not valid base64 data") from exc
    if not raw or len(raw) > max_bytes:
        raise BadRequestException(f"{label} is larger than {max_bytes // 1024} KB")
    if not _matches(kind, raw):
        raise BadRequestException(f"{label} content does not match its {kind.upper()} type")
    return f"data:image/{kind};base64,{body}"


def validate_https_url(value: Optional[str], label: str = "Link") -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    if not re.match(r"^https://[^\s/$.?#][^\s]*$", value, re.IGNORECASE) or len(value) > 2000:
        raise BadRequestException(f"{label} must be an https:// address")
    return value


def validate_csv_text(text: str, max_bytes: int = 5 * 1024 * 1024) -> str:
    if len(text.encode("utf-8")) > max_bytes:
        raise BadRequestException(f"CSV is larger than {max_bytes // (1024 * 1024)} MB")
    if "\x00" in text:
        raise BadRequestException("CSV must be plain text")
    return text
