"""Deterministic provider for local development and integration tests."""

from __future__ import annotations

from typing import Optional

from app.games.cricket.providers.base import CricketMatch


class MockCricketDataProvider:
    def __init__(self, matches: Optional[list[CricketMatch]] = None) -> None:
        if matches is None:
            matches = [
                CricketMatch(
                    "demo-match-upcoming",
                    "Falcons",
                    "Tigers",
                    "SCHEDULED",
                    metadata={"competition": "Local Demo League"},
                ),
                CricketMatch(
                    "demo-match-live",
                    "Sharks",
                    "Wolves",
                    "LIVE",
                    home_score="112/3 (14.2)",
                    away_score="Yet to bat",
                    metadata={"competition": "Local Demo League"},
                ),
            ]
        self.matches = {match.match_id: match for match in (matches or [])}

    async def list_matches(self) -> list[CricketMatch]:
        return list(self.matches.values())

    async def get_match(self, match_id: str) -> Optional[CricketMatch]:
        return self.matches.get(match_id)

    def update(self, match: CricketMatch) -> None:
        self.matches[match.match_id] = match
