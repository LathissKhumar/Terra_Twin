"""Custom exceptions and structured error handlers for TerraTwin."""

from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse


class TerraTwinError(Exception):
    """Base exception for all TerraTwin domain errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class DatasetNotFoundError(TerraTwinError):
    """Raised when a requested elevation dataset does not exist."""

    pass


class DatasetAcquisitionError(TerraTwinError):
    """Raised when a remote product cannot be fetched or verified."""

    pass


class InvalidRasterError(TerraTwinError):
    """Raised when an ingested raster fails validation (CRS, dimensions, NoData)."""

    pass


class CoordinateTransformationError(TerraTwinError):
    """Raised when coordinates or rasters cannot be safely transformed."""

    pass


class IncompatibleResolutionError(TerraTwinError):
    """Raised when comparing datasets with incompatible spatial supports without harmonization."""

    pass


class InsufficientCoverageError(TerraTwinError):
    """Raised when valid observation coverage does not meet scientific thresholds."""

    pass


class ReconstructionError(TerraTwinError):
    """Raised when 3D terrain mesh generation fails."""

    pass


class ValidationError(TerraTwinError):
    """Raised when independent elevation comparison fails."""

    pass


async def domain_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle custom domain exceptions and return standardized JSON error response."""
    status_code = status.HTTP_400_BAD_REQUEST
    if isinstance(exc, DatasetNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    if isinstance(exc, DatasetAcquisitionError):
        status_code = status.HTTP_502_BAD_GATEWAY

    message = exc.message if isinstance(exc, TerraTwinError) else str(exc)
    details = exc.details if isinstance(exc, TerraTwinError) else {}

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "type": exc.__class__.__name__,
                "message": message,
                "details": details,
                "path": request.url.path,
            }
        },
    )
