"""Provider contract and normalized cricket match shape."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass(frozen=True)
class CricketMatch:
    match_id: str
    home_team: str
    away_team: str
    status: str
    home_score: Optional[str] = None
    away_score: Optional[str] = None
    winner: Optional[str] = None
    abandoned: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class CricketDataProvider(Protocol):
    async def list_matches(self) -> list[CricketMatch]: ...

    async def get_match(self, match_id: str) -> Optional[CricketMatch]: ...
