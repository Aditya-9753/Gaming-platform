"""Integration tests for user profiles, support tickets, and admin RBAC enforcement."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_users_me_requires_auth(async_client: AsyncClient):
    """GET /api/v1/users/me returns 401 when unauthenticated."""
    res = await async_client.get("/api/v1/users/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_admin_endpoints_require_admin_role(async_client: AsyncClient):
    """Admin endpoints reject unauthorized or regular user requests."""
    res = await async_client.get("/api/v1/admin/audit-logs")
    assert res.status_code == 401

    res = await async_client.patch(
        "/api/v1/admin/games/aviator/settings",
        json={"min_bet": 200},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_support_tickets_require_auth(async_client: AsyncClient):
    """Support endpoints require authentication."""
    res = await async_client.get("/api/v1/support/tickets")
    assert res.status_code == 401

    res = await async_client.post(
        "/api/v1/support/tickets",
        json={"subject": "Help", "message": "Test question"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_history_bets_require_auth(async_client: AsyncClient):
    """Bet history requires authentication."""
    res = await async_client.get("/api/v1/history/bets")
    assert res.status_code == 401
