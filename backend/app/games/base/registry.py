"""Game engine registry managing dynamic plug-and-play game registration by code."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Type
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger

logger = get_logger("engine_registry")


class GameEngineRegistry:
    """Registry holding game engine classes and active engine instances by game code."""

    def __init__(self) -> None:
        self._engine_classes: Dict[str, Type] = {}
        self._instances: Dict[str, Any] = {}

    def register_class(self, game_code: str, engine_cls: Type) -> None:
        """Register an engine class by unique game code."""
        self._engine_classes[game_code.lower()] = engine_cls
        logger.info("Registered game engine class", game_code=game_code, cls=engine_cls.__name__)

    def register(self, engine: Any) -> None:
        """Register a running engine instance."""
        code = engine.game_id.lower()
        self._instances[code] = engine
        logger.info("Registered running game engine instance", game_code=code)

    def get(self, game_code: str) -> Optional[Any]:
        """Retrieve an active engine instance by game code."""
        return self._instances.get(game_code.lower())

    def get_class(self, game_code: str) -> Optional[Type]:
        """Retrieve registered engine class by game code."""
        return self._engine_classes.get(game_code.lower())

    def instantiate_all(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis,
        codes: Optional[List[str]] = None,
    ) -> List[Any]:
        """Instantiate registered engine classes (optionally only ``codes``)."""
        for code, cls in self._engine_classes.items():
            if codes is not None and code not in codes:
                continue
            if code not in self._instances:
                try:
                    instance = cls(session_factory=session_factory, redis=redis)
                    self._instances[code] = instance
                except Exception as exc:
                    logger.warning("Could not auto-instantiate engine", game=code, error=str(exc))
        return list(self._instances.values())

    def registered_codes(self) -> List[str]:
        """Game codes of all registered engine classes."""
        return list(self._engine_classes.keys())

    def list_engines(self) -> List[Any]:
        """List all active engine instances."""
        return list(self._instances.values())

    async def start_all(self) -> None:
        """Start all registered game engines."""
        for engine in self._instances.values():
            if hasattr(engine, "start"):
                engine.start()

    async def stop_all(self) -> None:
        """Stop all running game engines."""
        for engine in self._instances.values():
            if hasattr(engine, "stop"):
                await engine.stop()


# Global engine registry instance
engine_registry = GameEngineRegistry()


def register_game(code: str) -> Callable[[Type], Type]:
    """Decorator to register a game engine class by code."""
    def decorator(cls: Type) -> Type:
        engine_registry.register_class(code, cls)
        return cls
    return decorator
