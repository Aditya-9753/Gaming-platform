"""Tests for system health endpoints, security headers, and request ID middleware."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint_healthy(async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """Test /health when both database and Redis report healthy."""
    async def mock_db_health() -> bool:
        return True

    async def mock_redis_health() -> bool:
        return True

    monkeypatch.setattr("app.api.v1.health.check_db_health", mock_db_health)
    monkeypatch.setattr("app.api.v1.health.check_redis_health", mock_redis_health)

    response = await async_client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["checks"]["database"] == "up"
    assert data["checks"]["redis"] == "up"
    assert "version" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_endpoint_degraded(async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """Test /health when database reports down."""
    async def mock_db_down() -> bool:
        return False

    async def mock_redis_up() -> bool:
        return True

    monkeypatch.setattr("app.api.v1.health.check_db_health", mock_db_down)
    monkeypatch.setattr("app.api.v1.health.check_redis_health", mock_redis_up)

    response = await async_client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "degraded"
    assert data["checks"]["database"] == "down"
    assert data["checks"]["redis"] == "up"


@pytest.mark.asyncio
async def test_api_v1_health_route(async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """Test /api/v1/health prefix routing."""
    async def mock_db_health() -> bool:
        return True

    async def mock_redis_health() -> bool:
        return True

    monkeypatch.setattr("app.api.v1.health.check_db_health", mock_db_health)
    monkeypatch.setattr("app.api.v1.health.check_redis_health", mock_redis_health)

    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_root_endpoint(async_client: AsyncClient):
    """Test root status endpoint."""
    response = await async_client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "online"
    assert "name" in payload


@pytest.mark.asyncio
async def test_security_headers_and_request_id(async_client: AsyncClient):
    """Verify security headers and X-Request-ID propagation."""
    custom_id = "test-custom-trace-uuid-12345"
    response = await async_client.get("/health", headers={"X-Request-ID": custom_id})

    # Request ID reflection
    assert response.headers.get("x-request-id") == custom_id

    # Security headers
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("x-xss-protection") == "1; mode=block"
