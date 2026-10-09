"""SSRF guard for server-side requests to user- or admin-supplied URLs.

Only http(s) on standard ports, and every address the host resolves to must be public
(no loopback, private, link-local / cloud metadata, multicast, reserved or unspecified).
Callers must also disable redirects so a public URL cannot bounce to an internal one.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from app.core.exceptions import BadRequestException

_BLOCKED_HOSTS = ("localhost", "metadata.google.internal", "metadata")


def _resolves_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    if not infos:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if not ip.is_global or ip.is_multicast:
            return False
    return True


async def assert_public_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BadRequestException("Only http(s) URLs are allowed")
    if parts.port not in (None, 80, 443):
        raise BadRequestException("Only the standard ports 80 / 443 are allowed")
    if parts.username or parts.password:
        raise BadRequestException("URLs with credentials are not allowed")
    host = parts.hostname.lower().rstrip(".")
    if host in _BLOCKED_HOSTS or host.endswith((".local", ".internal", ".localhost")):
        raise BadRequestException("The address must be public")
    loop = asyncio.get_running_loop()
    if not await loop.run_in_executor(None, _resolves_public, host):
        raise BadRequestException("The address must resolve to a public IP")
    return url
