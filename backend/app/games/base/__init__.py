"""Base game engine abstractions, leader election, and settlement."""

from app.games.base.engine import BaseGameEngine
from app.games.base.leader import LeaderElection
from app.games.base.recovery import EngineRecoveryService
from app.games.base.registry import GameEngineRegistry, engine_registry, register_game
from app.games.base.settlement import RoundSettlementManager
from app.games.base.state import (
    EngineState,
    RedisRoundStateManager,
    RoundStateSnapshot,
    can_transition,
    validate_transition,
)

__all__ = [
    "BaseGameEngine",
    "LeaderElection",
    "EngineRecoveryService",
    "GameEngineRegistry",
    "engine_registry",
    "register_game",
    "RoundSettlementManager",
    "EngineState",
    "RedisRoundStateManager",
    "RoundStateSnapshot",
    "can_transition",
    "validate_transition",
]
