"""Health check response schemas."""

from pydantic import BaseModel, Field


class DatabaseHealth(BaseModel):
    """Database connectivity and spatial extension status."""

    connected: bool
    database_version: str | None = None
    postgis_available: bool
    postgis_version: str | None = None
    error: str | None = None


class SystemInfo(BaseModel):
    """Runtime and environment information."""

    environment: str
    debug: bool
    python_version: str


class HealthResponse(BaseModel):
    """Top-level health check response schema."""

    status: str = Field(..., description="Overall health status: 'healthy' or 'degraded'")
    app_name: str
    version: str
    system: SystemInfo
    database: DatabaseHealth
