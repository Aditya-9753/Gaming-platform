"""Keep a free-plan web service awake by calling its own public health check.

Render's free plan stops a service after 15 minutes without incoming requests; the next
visitor then waits up to a minute while it starts again (and the live games and affiliate
jobs that run inside the API stop meanwhile). Render sets ``RENDER_EXTERNAL_URL`` to the
service's public address; a request to it goes through Render's proxy, so it counts as
traffic. GitHub's scheduled keep-alive alone is not enough: GitHub often delays scheduled
runs by hours.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import httpx

from app.core.logging import get_logger

logger = get_logger("keep_awake")

INTERVAL_SECONDS = 10 * 60  # well inside Render's 15-minute idle limit


def target_url() -> Optional[str]:
    """The public /health URL to call, or None when not running on Render (or switched off)."""
    if os.environ.get("KEEP_AWAKE", "true").strip().lower() in ("0", "false", "no", "off"):
        return None
    base = (os.environ.get("KEEP_AWAKE_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if not base.startswith("https://"):
        return None
    return f"{base}/health"


async def keep_awake_loop(url: str, interval: float = INTERVAL_SECONDS) -> None:
    logger.info("Keep-awake health check enabled", url=url, every_seconds=interval)
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "keep-awake/1.0"}) as client:
        while True:
            await asyncio.sleep(interval)
            try:
                response = await client.get(url)
                if response.status_code >= 400:
                    logger.warning("Keep-awake health check failed", status=response.status_code)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # a missed ping is harmless; try again next round
                logger.warning("Keep-awake health check error", error=str(exc))
