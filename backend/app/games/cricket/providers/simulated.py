"""Time-driven simulated cricket feed for local/dev play.

Every CYCLE_SECONDS a new match is scheduled. Each match goes through:

    SCHEDULED  (winner market open)      BETTING_SECONDS
    LIVE       (ball-by-ball scoring)    LIVE_SECONDS (two 5-over innings)
    COMPLETED  (winner known, settled)

Match k opens at ``k * CYCLE_SECONDS``; its market closes exactly when match
k+1 opens, so there is always one market open for predictions.
Ball outcomes are derived from HMAC(secret, match_id, ball_no), so the result
is deterministic for a given secret and the state can be recomputed from the
clock alone (no in-memory state; survives restarts and multiple workers).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Callable, List, Optional, Tuple

from app.games.cricket.providers.base import CricketMatch

TEAMS = [
    "Mumbai Mavericks", "Delhi Daredevils", "Chennai Chargers", "Kolkata Knights",
    "Bengaluru Blasters", "Punjab Panthers", "Rajasthan Royals XI", "Hyderabad Hawks",
    "Lucknow Lions", "Gujarat Giants",
]

OVERS_PER_INNINGS = 5
BALLS_PER_INNINGS = OVERS_PER_INNINGS * 6
MAX_WICKETS = 10

# Betting window == cycle length, so exactly one market is always open while
# the previous match is being played out.
CYCLE_SECONDS = 150
BETTING_SECONDS = CYCLE_SECONDS
SECONDS_PER_BALL = 2
LIVE_SECONDS = BALLS_PER_INNINGS * 2 * SECONDS_PER_BALL  # 120s
RESULT_VISIBLE_SECONDS = 300

# Weighted ball outcomes (sum = 100): dot, 1, 2, 3, 4, 6, W
_OUTCOMES: List[Tuple[str, int]] = [
    ("0", 30), ("1", 28), ("2", 12), ("3", 3), ("4", 13), ("6", 7), ("W", 7),
]


def _ball(secret: bytes, match_id: str, innings: int, ball: int) -> str:
    digest = hmac.new(secret, f"{match_id}:{innings}:{ball}".encode(), hashlib.sha256).digest()
    roll = int.from_bytes(digest[:4], "big") % 100
    for outcome, weight in _OUTCOMES:
        if roll < weight:
            return outcome
        roll -= weight
    return "0"


def _overs(balls: int) -> str:
    return f"{balls // 6}.{balls % 6}"


class _Innings:
    def __init__(self) -> None:
        self.runs = 0
        self.wickets = 0
        self.balls = 0
        self.log: List[str] = []

    @property
    def all_out(self) -> bool:
        return self.wickets >= MAX_WICKETS

    def add(self, outcome: str) -> None:
        self.balls += 1
        self.log.append(outcome)
        if outcome == "W":
            self.wickets += 1
        else:
            self.runs += int(outcome)

    def score(self) -> str:
        return f"{self.runs}/{self.wickets} ({_overs(self.balls)})"


class SimulatedCricketDataProvider:
    """Deterministic, clock-driven cricket provider."""

    def __init__(self, secret: str, clock: Callable[[], float] = time.time) -> None:
        self._secret = secret.encode() or b"dev-cricket"
        self._clock = clock

    # -- helpers ---------------------------------------------------------
    def _teams(self, k: int) -> Tuple[str, str]:
        digest = hmac.new(self._secret, f"teams:{k}".encode(), hashlib.sha256).digest()
        home = digest[0] % len(TEAMS)
        away = (home + 1 + digest[1] % (len(TEAMS) - 1)) % len(TEAMS)
        return TEAMS[home], TEAMS[away]

    def _build(self, k: int, now: float) -> CricketMatch:
        match_id = f"sim-{k}"
        home, away = self._teams(k)
        opens_at = k * CYCLE_SECONDS
        live_at = opens_at + BETTING_SECONDS
        ends_at = live_at + LIVE_SECONDS
        meta = {
            "competition": "Virtual Premier League (T5)",
            "category": "Virtual League",
            "source": "simulated",
            "format": f"T{OVERS_PER_INNINGS}",
            "betting_closes_at": live_at,
            "ends_at": ends_at,
        }

        if now < live_at:
            return CricketMatch(match_id, home, away, "SCHEDULED", metadata=meta)

        balls_elapsed = int((min(now, ends_at) - live_at) // SECONDS_PER_BALL)
        first, second = _Innings(), _Innings()
        target: Optional[int] = None
        chased = False

        for i in range(BALLS_PER_INNINGS):
            if balls_elapsed <= 0 or first.all_out:
                break
            first.add(_ball(self._secret, match_id, 1, i))
            balls_elapsed -= 1
        first_done = first.all_out or first.balls >= BALLS_PER_INNINGS
        if first_done:
            target = first.runs + 1
            # Second innings starts on the clock slot after the first's 30 balls.
            balls_elapsed = int((min(now, ends_at) - live_at) // SECONDS_PER_BALL) - BALLS_PER_INNINGS
            for i in range(BALLS_PER_INNINGS):
                if balls_elapsed <= 0 or second.all_out or second.runs >= target:
                    break
                second.add(_ball(self._secret, match_id, 2, i))
                balls_elapsed -= 1
            chased = second.runs >= target

        second_done = first_done and (
            chased or second.all_out or second.balls >= BALLS_PER_INNINGS
        )
        finished = second_done or now >= ends_at

        current = second if first_done and second.balls > 0 else first
        over_start = (current.balls - 1) // 6 * 6 if current.balls else 0
        meta.update(
            {
                "batting": away if current is second else home,
                "target": target,
                "this_over": current.log[over_start:],
                "last_ball": current.log[-1] if current.log else None,
            }
        )
        home_score = first.score()
        away_score = second.score() if first_done else "Yet to bat"

        if not finished:
            return CricketMatch(match_id, home, away, "LIVE", home_score, away_score, metadata=meta)

        if chased:
            winner = away
            meta["result"] = f"{away} won by {MAX_WICKETS - second.wickets} wickets"
        elif second.runs == first.runs:
            # Tie → super-over decided by seed
            winner = home if _ball(self._secret, match_id, 3, 0) in {"4", "6"} else away
            meta["result"] = f"Match tied — {winner} won the super over"
        else:
            winner = home
            meta["result"] = f"{home} won by {first.runs - second.runs} runs"
        return CricketMatch(match_id, home, away, "COMPLETED", home_score, away_score, winner=winner, metadata=meta)

    # -- provider contract ---------------------------------------------
    async def list_matches(self) -> list[CricketMatch]:
        now = self._clock()
        current = int(now // CYCLE_SECONDS)
        matches = []
        for k in range(max(0, current - 3), current + 1):
            match = self._build(k, now)
            ends_at = match.metadata["ends_at"]
            if match.status == "COMPLETED" and now - ends_at > RESULT_VISIBLE_SECONDS:
                continue
            matches.append(match)
        order = {"LIVE": 0, "SCHEDULED": 1, "COMPLETED": 2}
        return sorted(matches, key=lambda m: (order.get(m.status, 3), m.match_id))

    async def get_match(self, match_id: str) -> Optional[CricketMatch]:
        if not match_id.startswith("sim-"):
            return None
        try:
            k = int(match_id[4:])
        except ValueError:
            return None
        now = self._clock()
        if k < 0 or k * CYCLE_SECONDS > now:
            return None
        return self._build(k, now)
