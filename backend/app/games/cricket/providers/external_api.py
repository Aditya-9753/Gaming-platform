"""HTTP cricket data adapter with bounded timeout, cache, and retries."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional
from urllib.parse import quote

import httpx

from app.core.exceptions import ServiceUnavailableException
from app.games.cricket.providers.base import CricketMatch


class ExternalCricketDataProvider:
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout_seconds: float = 3.0,
        retries: int = 2,
        cache_ttl_seconds: float = 5.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.retries = max(0, retries)
        self.cache_ttl_seconds = cache_ttl_seconds
        self.client = client
        self._cache: dict[str, tuple[float, Any]] = {}

    async def _get(self, path: str) -> Any:
        now = time.monotonic()
        cached = self._cache.get(path)
        if cached and cached[0] > now:
            return cached[1]
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            for attempt in range(self.retries + 1):
                try:
                    response = await client.get(
                        f"{self.base_url}/{path.lstrip('/')}", headers=headers
                    )
                    if response.status_code == 429:
                        if attempt == self.retries:
                            raise ServiceUnavailableException(
                                "Cricket provider rate limit reached"
                            )
                        try:
                            retry_after = float(response.headers.get("Retry-After", 1))
                        except ValueError:
                            retry_after = 1.0
                        retry_after = min(max(retry_after, 0.0), 3.0)
                        await asyncio.sleep(max(0, retry_after))
                        continue
                    response.raise_for_status()
                    payload = response.json()
                    self._cache[path] = (now + self.cache_ttl_seconds, payload)
                    return payload
                except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                    if attempt == self.retries:
                        raise ServiceUnavailableException(
                            "Cricket data provider is unavailable"
                        ) from exc
                    await asyncio.sleep(0.1 * (2**attempt))
            raise ServiceUnavailableException("Cricket data provider is unavailable")
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _match(data: dict[str, Any]) -> CricketMatch:
        return CricketMatch(
            match_id=str(data["id"]),
            home_team=str(data["home_team"]),
            away_team=str(data["away_team"]),
            status=str(data["status"]).upper(),
            home_score=data.get("home_score"),
            away_score=data.get("away_score"),
            winner=data.get("winner"),
            abandoned=bool(data.get("abandoned", False)),
            metadata=data,
        )

    async def list_matches(self) -> list[CricketMatch]:
        payload = await self._get("matches")
        return [self._match(item) for item in payload.get("matches", [])]

    async def get_match(self, match_id: str) -> Optional[CricketMatch]:
        payload = await self._get(f"matches/{quote(match_id, safe='')}")
        item = payload.get("match", payload)
        return self._match(item) if item else None
