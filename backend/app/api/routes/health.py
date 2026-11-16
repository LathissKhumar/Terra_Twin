"""Health check endpoint implementation."""

import platform

from fastapi import APIRouter, Depends, Response

from app.core.config import settings
from app.database.session import check_database_health
from app.domain.schemas.health import DatabaseHealth, HealthResponse, SystemInfo

router = APIRouter(prefix="/health", tags=["Health"])


@router.api_route(
    "",
    methods=["GET", "HEAD"],
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse}},
)
async def get_health(
    response: Response,
    database: DatabaseHealth = Depends(check_database_health),
) -> HealthResponse:
    """Report API and dependency readiness without exposing connection details."""
    healthy = database.connected and database.postgis_available
    response.status_code = 200 if healthy else 503
    response.headers["Cache-Control"] = "no-store"
    return HealthResponse(
        status="healthy" if healthy else "degraded",
        app_name=settings.PROJECT_NAME,
        version=settings.VERSION,
        system=SystemInfo(
            environment=settings.ENVIRONMENT,
            debug=settings.DEBUG,
            python_version=platform.python_version(),
        ),
        database=database,
    )
