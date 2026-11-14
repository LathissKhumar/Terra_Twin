"""Tests for the health endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint_structure():
    """Verify health endpoint returns a valid schema and required fields."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()

    # Verify top-level structure
    assert "status" in data
    assert data["status"] in ["healthy", "degraded"]
    assert data["app_name"] == "TerraTwin"
    assert "version" in data

    # Verify system sub-object
    assert "system" in data
    assert "environment" in data["system"]
    assert "python_version" in data["system"]

    # Verify database sub-object
    assert "database" in data
    assert "connected" in data["database"]
    assert "postgis_available" in data["database"]


@pytest.mark.asyncio
async def test_root_endpoint():
    """Verify root discovery endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "TerraTwin"
    assert "/api/v1/docs" in data["docs"]
    assert "/api/v1/health" in data["health"]