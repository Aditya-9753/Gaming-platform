"""The caller's real IP behind the hosting proxy.

``X-Forwarded-For`` is "client, proxy1, proxy2"; entries on the left can be forged by the
client, entries on the right are appended by proxies we trust. With ``TRUSTED_PROXY_HOPS``
proxies in front of the app (1 on Render), the real client is that many entries from the right.
Without the header (local development, tests) the socket peer is used.
"""

from __future__ import annotations

from typing import Mapping, Optional

from app.core.config import get_settings


def from_headers(headers: Mapping[str, str], peer: Optional[str]) -> str:
    hops = get_settings().TRUSTED_PROXY_HOPS
    forwarded = [part.strip() for part in (headers.get("x-forwarded-for") or "").split(",") if part.strip()]
    if hops > 0 and forwarded:
        return forwarded[-hops] if len(forwarded) >= hops else forwarded[0]
    return peer or "unknown"


def of_request(request) -> str:
    return from_headers({k.lower(): v for k, v in request.headers.items()}, request.client.host if request.client else None)
