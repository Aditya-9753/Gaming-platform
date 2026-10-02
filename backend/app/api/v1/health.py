"""Health check endpoints verifying application, database, and Redis connectivity."""

from datetime import datetime, timezone
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.database import check_db_health
from app.core.redis import check_redis_health

router = APIRouter()


class HealthChecks(BaseModel):
    """Component-level health check statuses."""

    database: str = Field(description="Database connectivity status: 'up' or 'down'")
    redis: str = Field(description="Redis connectivity status: 'up' or 'down'")


class HealthResponse(BaseModel):
    """Standardized health check response payload."""

    status: str = Field(description="System status: 'healthy' or 'degraded'")
    version: str = Field(default="1.0.0", description="API release version")
    timestamp: str = Field(description="UTC timestamp of the check in ISO-8601 format")
    checks: HealthChecks


import asyncio


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def get_health() -> HealthResponse:
    """Perform concurrent health checks on database and Redis and return system status."""
    db_ok, redis_ok = await asyncio.gather(
        check_db_health(),
        check_redis_health(),
        return_exceptions=False,
    )

    is_healthy = db_ok and redis_ok

    return HealthResponse(
        status="healthy" if is_healthy else "degraded",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks=HealthChecks(
            database="up" if db_ok else "down",
            redis="up" if redis_ok else "down",
        ),
    )
