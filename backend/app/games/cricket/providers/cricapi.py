"""Real cricket feed from CricketData.org (CricAPI v1) — every match worldwide.

Free keys allow ~100 calls/day, so responses are cached in-process:

* ``currentMatches`` (live + recent + near upcoming) every ``live_refresh``
  seconds (default 1000s ≈ 86 calls/day),
* ``matches`` (upcoming fixtures) every ``schedule_refresh`` seconds
  (default 3h ≈ 8 calls/day).

On a paid plan set CRICAPI_LIVE_REFRESH_SECONDS=30 for near real-time scores.
Failures keep serving the last good data.
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.core.exceptions import ServiceUnavailableException
from app.core.logging import get_logger
from app.games.cricket.providers.base import CricketMatch

logger = get_logger("cricapi")

BASE_URL = "https://api.cricapi.com/v1"
ID_PREFIX = "ca-"

# ICC full + leading associate members (for the "International" category)
NATIONS = {
    "india", "australia", "england", "pakistan", "south africa", "new zealand", "sri lanka",
    "bangladesh", "west indies", "afghanistan", "zimbabwe", "ireland", "scotland", "netherlands",
    "nepal", "oman", "namibia", "united arab emirates", "uae", "usa", "united states of america",
    "canada", "papua new guinea", "hong kong", "kenya", "uganda", "jersey", "italy",
}
LEAGUE_HINTS = (
    "premier league", "ipl", "big bash", "bbl", "caribbean premier", "cpl", "psl", "sa20",
    "the hundred", "super smash", "t20 blast", "vitality blast", "ilt20", "major league cricket",
    "lanka premier", "bangladesh premier", " league",
)
NO_RESULT = re.compile(r"no result|abandon|match drawn|\bdrawn\b|tied|cancel", re.IGNORECASE)


def categorise(name: str, teams: list[str], match_type: str) -> str:
    lowered = name.lower()
    if "women" in lowered or any("women" in t.lower() for t in teams):
        return "Women"
    if any(hint in lowered for hint in LEAGUE_HINTS) and match_type.lower() in ("t20", "t10", "t20i", ""):
        return "T20 Leagues"
    base = [re.sub(r"\s+(a|u19|u-19|xi|emerging)$", "", t.lower()).strip() for t in teams]
    if base and all(t in NATIONS for t in base):
        return "International"
    return "Domestic"


def _score_for(team: str, scores: list[dict[str, Any]]) -> Optional[str]:
    parts = []
    for s in scores or []:
        inning = str(s.get("inning", "")).lower()
        if inning.startswith(team.lower()):
            parts.append(f"{s.get('r', 0)}/{s.get('w', 0)} ({s.get('o', 0)})")
    return " & ".join(parts) or None


def _winner(status_text: str, teams: list[str]) -> Optional[str]:
    lowered = status_text.lower()
    if " won" not in lowered:
        return None
    for team in sorted(teams, key=len, reverse=True):
        if lowered.startswith(team.lower()):
            return team
    return None


def to_match(item: dict[str, Any]) -> Optional[CricketMatch]:
    teams = [str(t) for t in (item.get("teams") or [])]
    if len(teams) < 2 or not item.get("id"):
        return None
    status_text = str(item.get("status") or "")
    started, ended = bool(item.get("matchStarted")), bool(item.get("matchEnded"))
    winner = _winner(status_text, teams) if ended else None
    abandoned = ended and winner is None and bool(NO_RESULT.search(status_text))
    status = "COMPLETED" if ended else "LIVE" if started else "SCHEDULED"
    starts_at = None
    if item.get("dateTimeGMT"):
        try:
            starts_at = datetime.fromisoformat(str(item["dateTimeGMT"]).replace("Z", "")).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            starts_at = None
    match_type = str(item.get("matchType") or "")
    logos = {str(t.get("name")): t.get("img") for t in (item.get("teamInfo") or []) if t.get("name")}
    return CricketMatch(
        match_id=f"{ID_PREFIX}{item['id']}",
        home_team=teams[0],
        away_team=teams[1],
        status=status,
        home_score=_score_for(teams[0], item.get("score") or []),
        away_score=_score_for(teams[1], item.get("score") or []),
        winner=winner,
        abandoned=abandoned,
        metadata={
            "competition": item.get("name"),
            "category": categorise(str(item.get("name") or ""), teams, match_type),
            "format": match_type.upper() or None,
            "venue": item.get("venue"),
            "result": status_text or None,
            "betting_closes_at": starts_at,
            "starts_at": starts_at,
            "logos": logos,
            "source": "cricapi",
        },
    )


class CricApiProvider:
    def __init__(
        self,
        api_key: str,
        live_refresh: float = 1000,
        schedule_refresh: float = 10800,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.api_key = api_key
        self.live_refresh = live_refresh
        self.schedule_refresh = schedule_refresh
        self.client = client
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def _fetch(self, endpoint: str, ttl: float) -> list[dict[str, Any]]:
        cached = self._cache.get(endpoint)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        lock = self._locks.setdefault(endpoint, asyncio.Lock())
        async with lock:
            cached = self._cache.get(endpoint)
            if cached and cached[0] > time.monotonic():
                return cached[1]
            client = self.client or httpx.AsyncClient(timeout=8.0)
            try:
                response = await client.get(f"{BASE_URL}/{endpoint}", params={"apikey": self.api_key, "offset": 0})
                payload = response.json()
                if payload.get("status") != "success":
                    raise ValueError(payload.get("reason") or "CricAPI request failed")
                data = payload.get("data") or []
                info = payload.get("info") or {}
                logger.info("CricAPI refreshed", endpoint=endpoint, matches=len(data),
                            hits_today=info.get("hitsToday"), hits_limit=info.get("hitsLimit"))
                self._cache[endpoint] = (time.monotonic() + ttl, data)
                return data
            except Exception as exc:
                logger.warning("CricAPI request failed; serving cached data", endpoint=endpoint, error=str(exc))
                if cached:
                    # back off for a minute before retrying
                    self._cache[endpoint] = (time.monotonic() + 60, cached[1])
                    return cached[1]
                raise ServiceUnavailableException(f"Cricket data provider unavailable: {exc}") from exc
            finally:
                if self.client is None:
                    await client.aclose()

    async def list_matches(self) -> list[CricketMatch]:
        current = await self._fetch("currentMatches", self.live_refresh)
        try:
            upcoming = await self._fetch("matches", self.schedule_refresh)
        except ServiceUnavailableException:
            upcoming = []
        seen: dict[str, CricketMatch] = {}
        # currentMatches has fresher scores, so it wins over the schedule list
        for item in [*upcoming, *current]:
            match = to_match(item)
            if match:
                seen[match.match_id] = match
        now = time.time()
        result = []
        for m in seen.values():
            starts_at = m.metadata.get("starts_at")
            if m.status == "SCHEDULED" and starts_at and starts_at > now + 14 * 86400:
                continue  # too far ahead
            if m.status == "SCHEDULED" and starts_at and starts_at <= now:
                # Cached data can lag: once the start time passes the market is closed
                m = dataclasses.replace(m, status="LIVE")
            result.append(m)
        return result

    async def get_match(self, match_id: str) -> Optional[CricketMatch]:
        if not match_id.startswith(ID_PREFIX):
            return None
        for match in await self.list_matches():
            if match.match_id == match_id:
                return match
        return None
