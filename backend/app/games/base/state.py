"""Game round state machine, validation, and Redis state persistence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from redis.asyncio import Redis

from app.core.constants import GameRoundLifecycle, RoundStatus
from app.core.exceptions import BadRequestException


class EngineState(str, Enum):
    """Lifecycle state of a game engine worker."""

    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"


# Allowed state transitions for GameRound
VALID_ROUND_TRANSITIONS: Dict[str, Set[str]] = {
    RoundStatus.SCHEDULED.value: {
        RoundStatus.BETTING.value,
        GameRoundLifecycle.WAITING.value,
        GameRoundLifecycle.CREATED.value,
        RoundStatus.CANCELLED.value,
    },
    GameRoundLifecycle.WAITING.value: {
        GameRoundLifecycle.BETTING_OPEN.value,
        RoundStatus.CANCELLED.value,
    },
    GameRoundLifecycle.BETTING_OPEN.value: {
        RoundStatus.RUNNING.value,
        RoundStatus.CANCELLED.value,
    },
    GameRoundLifecycle.CREATED.value: {
        GameRoundLifecycle.OPEN.value,
        RoundStatus.CANCELLED.value,
    },
    GameRoundLifecycle.OPEN.value: {
        GameRoundLifecycle.LOCKED.value,
        RoundStatus.CANCELLED.value,
    },
    GameRoundLifecycle.LOCKED.value: {
        GameRoundLifecycle.RESULT.value,
        RoundStatus.CANCELLED.value,
    },
    RoundStatus.BETTING.value: {
        RoundStatus.RUNNING.value,
        RoundStatus.CANCELLED.value,
    },
    RoundStatus.RUNNING.value: {
        GameRoundLifecycle.CRASHED.value,
        GameRoundLifecycle.SETTLING.value,
        RoundStatus.COMPLETED.value,
        RoundStatus.CANCELLED.value,
    },
    GameRoundLifecycle.CRASHED.value: {
        GameRoundLifecycle.SETTLING.value,
        GameRoundLifecycle.HISTORY.value,
    },
    GameRoundLifecycle.SETTLING.value: {
        GameRoundLifecycle.HISTORY.value,
        RoundStatus.COMPLETED.value,
    },
    GameRoundLifecycle.RESULT.value: {
        GameRoundLifecycle.SETTLED.value,
        RoundStatus.CANCELLED.value,
    },
    GameRoundLifecycle.SETTLED.value: {
        GameRoundLifecycle.HISTORY.value,
    },
    GameRoundLifecycle.HISTORY.value: set(),
    RoundStatus.COMPLETED.value: set(),  # Terminal state
    RoundStatus.CANCELLED.value: set(),  # Terminal state
}


def can_transition(current_status: str, next_status: str) -> bool:
    """Return True if transitioning from current_status to next_status is valid."""
    allowed = VALID_ROUND_TRANSITIONS.get(current_status, set())
    return next_status in allowed


def validate_transition(current_status: str, next_status: str) -> None:
    """Raise BadRequestException if state transition is invalid."""
    if not can_transition(current_status, next_status):
        raise BadRequestException(
            f"Invalid round state transition from '{current_status}' to '{next_status}'"
        )


@dataclass
class RoundStateSnapshot:
    """Snapshot of an active game round stored in Redis and returned on WS resync."""

    round_id: str
    game_id: str
    round_no: int
    status: str
    server_seed_hash: str
    started_at: Optional[str] = None
    bet_count: int = 0
    total_wagered: int = 0
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RoundStateSnapshot:
        return cls(
            round_id=data["round_id"],
            game_id=data["game_id"],
            round_no=int(data["round_no"]),
            status=data["status"],
            server_seed_hash=data["server_seed_hash"],
            started_at=data.get("started_at"),
            bet_count=int(data.get("bet_count", 0)),
            total_wagered=int(data.get("total_wagered", 0)),
            metadata=data.get("metadata"),
        )


class RedisRoundStateManager:
    """Persists real-time round state and open wagers in Redis for instant query and WS resync."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    def _state_key(self, game_id: str) -> str:
        return f"game:{game_id}:state"

    def _bets_key(self, game_id: str, round_id: str) -> str:
        return f"game:{game_id}:round:{round_id}:bets"

    async def set_round_state(
        self,
        game_id: str,
        round_id: str,
        round_no: int,
        status: str,
        server_seed_hash: str,
        started_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RoundStateSnapshot:
        """Store active round state snapshot in Redis with 1-hour expiry."""
        started_str = started_at.isoformat() if started_at else datetime.now(timezone.utc).isoformat()
        snapshot = RoundStateSnapshot(
            round_id=round_id,
            game_id=game_id,
            round_no=round_no,
            status=status,
            server_seed_hash=server_seed_hash,
            started_at=started_str,
            metadata=metadata or {},
        )
        key = self._state_key(game_id)
        await self.redis.set(key, json.dumps(snapshot.to_dict()), ex=3600)
        return snapshot

    async def get_round_state(self, game_id: str) -> Optional[RoundStateSnapshot]:
        """Fetch current round state snapshot from Redis."""
        key = self._state_key(game_id)
        raw = await self.redis.get(key)
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return RoundStateSnapshot.from_dict(data)

    async def update_status(self, game_id: str, new_status: str) -> Optional[RoundStateSnapshot]:
        """Update status of the currently active round in Redis."""
        current = await self.get_round_state(game_id)
        if not current:
            return None
        validate_transition(current.status, new_status)
        current.status = new_status
        key = self._state_key(game_id)
        await self.redis.set(key, json.dumps(current.to_dict()), ex=3600)
        return current

    async def add_open_bet(
        self,
        game_id: str,
        round_id: str,
        entry_id: str,
        user_id: str,
        bet_amount: int,
        selection: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Track open bet in Redis for active round and increment metrics."""
        bet_payload = {
            "entry_id": entry_id,
            "user_id": user_id,
            "bet_amount": bet_amount,
            "selection": selection or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        bets_key = self._bets_key(game_id, round_id)
        await self.redis.rpush(bets_key, json.dumps(bet_payload))
        await self.redis.expire(bets_key, 3600)

        # Update snapshot count
        current = await self.get_round_state(game_id)
        if current and current.round_id == round_id:
            current.bet_count += 1
            current.total_wagered += bet_amount
            await self.redis.set(self._state_key(game_id), json.dumps(current.to_dict()), ex=3600)

    async def get_open_bets(self, game_id: str, round_id: str) -> List[Dict[str, Any]]:
        """Fetch list of all open bets for a round from Redis."""
        bets_key = self._bets_key(game_id, round_id)
        items = await self.redis.lrange(bets_key, 0, -1)
        res = []
        for it in items:
            if isinstance(it, bytes):
                it = it.decode("utf-8")
            res.append(json.loads(it))
        return res

    async def clear_round_state(self, game_id: str) -> None:
        """Clear active round state from Redis upon settlement."""
        await self.redis.delete(self._state_key(game_id))
