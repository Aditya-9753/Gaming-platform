"""Async SQLAlchemy 2.0 database engine, session factory, and lifecycle helpers."""

from typing import Any, AsyncGenerator, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("database")


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""
    pass


# Global engine and sessionmaker references
engine: Optional[AsyncEngine] = None
async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    """Return active async engine or create one."""
    global engine, async_session_factory
    if engine is None:
        settings = get_settings()
        engine_kwargs: dict[str, Any] = {
            "echo": settings.DEBUG and settings.is_development,
            "future": True,
        }

        # Apply connection pooling options for non-SQLite databases (PostgreSQL/MySQL)
        if "sqlite" not in settings.DATABASE_URL:
            engine_kwargs.update(
                {
                    "pool_size": settings.DATABASE_POOL_SIZE,
                    "max_overflow": settings.DATABASE_MAX_OVERFLOW,
                    "pool_timeout": settings.DATABASE_POOL_TIMEOUT,
                    "pool_pre_ping": True,
                }
            )

        database_url = settings.DATABASE_URL
        if database_url.startswith("postgres://"):
            database_url = database_url.replace(
                "postgres://", "postgresql+asyncpg://", 1
            )
        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        engine = create_async_engine(database_url, **engine_kwargs)
        async_session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return active async sessionmaker."""
    global async_session_factory
    if async_session_factory is None:
        get_engine()
    assert async_session_factory is not None
    return async_session_factory


async def init_db() -> None:
    """Initialize database engine and verify connectivity."""
    get_engine()
    logger.info("Database engine initialized")


async def close_db() -> None:
    """Dispose of the database engine pool on application shutdown."""
    global engine, async_session_factory
    if engine is not None:
        await engine.dispose()
        engine = None
        async_session_factory = None
        logger.info("Database engine disposed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an async database session per request."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


import asyncio


async def _run_db_ping() -> bool:
    current_engine = get_engine()
    async with current_engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        return result.scalar() == 1


async def check_db_health(timeout: float = 2.0) -> bool:
    """Execute a simple SELECT 1 query with timeout to verify database health."""
    try:
        return await asyncio.wait_for(_run_db_ping(), timeout=timeout)
    except Exception as exc:
        logger.warning("Database health check failed", error=str(exc))
        return False
