"""Tests for the health endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database.session import check_database_health
from app.domain.schemas.health import DatabaseHealth
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint_structure():
    """Verify health endpoint returns a valid schema and required fields."""

    async def healthy_database():
        return DatabaseHealth(
            connected=True, database_version="test", postgis_available=True, postgis_version="test"
        )

    app.dependency_overrides[check_database_health] = healthy_database
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
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
        # JSON fallback when no HTML requested
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["app"] == "TerraTwin"
        assert "/api/v1/docs" in data["docs"]
        assert "/api/v1/health" in data["health"]

        # HTML console when browser requests text/html
        html_response = await client.get("/", headers={"Accept": "text/html,application/xhtml+xml"})
        assert html_response.status_code == 200
        assert "text/html" in html_response.headers["content-type"]
        assert "TerraTwin" in html_response.text
        assert "Planetary Analogue Discovery" in html_response.text

        # Explicit /console and /docs redirects
        console_res = await client.get("/console")
        assert console_res.status_code == 200
        assert "text/html" in console_res.headers["content-type"]

        docs_res = await client.get("/docs", follow_redirects=False)
        assert docs_res.status_code in [302, 307]
        assert "/api/v1/docs" in docs_res.headers["location"]

        # HEAD request on health endpoint
        head_res = await client.head("/api/v1/health")
        assert head_res.status_code in [200, 503]
