"""TerraTwin FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.api.api_v1 import api_router
from app.api.console_html import get_console_html
from app.core.config import settings
from app.core.exceptions import TerraTwinError, domain_exception_handler
from app.core.logging import get_logger, setup_logging
from app.services.discovery_jobs import start_job_runner, stop_job_runner

# Initialize structured logging
setup_logging()
logger = get_logger("terratwin.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle management."""
    logger.info(
        "Starting TerraTwin API server",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
    )
    start_job_runner()
    yield
    stop_job_runner()
    logger.info("Shutting down TerraTwin API server")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register custom exception handlers
app.add_exception_handler(TerraTwinError, domain_exception_handler)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "error": {
                "type": "HttpError",
                "message": str(exc.detail),
                "details": None,
                "path": request.url.path,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    fields = [{"location": list(error["loc"]), "type": error["type"]} for error in exc.errors()]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": {
                "type": "RequestValidationError",
                "message": "Invalid request",
                "details": {"fields": fields},
                "path": request.url.path,
            }
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Unhandled internal exception fallback."""
    logger.error(
        "Unhandled internal server error",
        exception_type=type(exc).__name__,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "type": "InternalServerError",
                "message": "An unexpected scientific processing error occurred.",
                "details": None,
                "path": request.url.path,
            }
        },
    )


# Mount versioned API routes
app.include_router(api_router, prefix=settings.API_V1_STR)


def should_render_html(request: Request) -> bool:
    fmt = request.query_params.get("format", "").lower()
    if fmt == "json":
        return False
    if fmt == "html":
        return True
    accept = request.headers.get("accept", "")
    return "text/html" in accept and not accept.startswith("application/json") and accept != "*/*"


@app.api_route("/", methods=["GET", "HEAD"], tags=["Root"], response_model=None)
async def root(request: Request) -> Response:
    """Root endpoint: serves interactive scientific console in browser, JSON otherwise."""
    if should_render_html(request):
        return HTMLResponse(
            content=get_console_html(version=settings.VERSION, environment=settings.ENVIRONMENT)
        )
    return JSONResponse(
        content={
            "app": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "docs": f"{settings.API_V1_STR}/docs",
            "health": f"{settings.API_V1_STR}/health",
            "console": "/console",
            "frontend": "https://frontend-alpha-azure-30.vercel.app",
        }
    )


@app.get("/console", include_in_schema=False)
@app.get("/dashboard", include_in_schema=False)
async def web_console() -> HTMLResponse:
    """Explicitly render the interactive web console."""
    return HTMLResponse(
        content=get_console_html(version=settings.VERSION, environment=settings.ENVIRONMENT)
    )


@app.get("/docs", include_in_schema=False)
async def redirect_docs() -> RedirectResponse:
    """Redirect top-level /docs to versioned API documentation."""
    return RedirectResponse(url=f"{settings.API_V1_STR}/docs")


@app.get("/redoc", include_in_schema=False)
async def redirect_redoc() -> RedirectResponse:
    """Redirect top-level /redoc to versioned ReDoc documentation."""
    return RedirectResponse(url=f"{settings.API_V1_STR}/redoc")


@app.get("/openapi.json", include_in_schema=False)
async def redirect_openapi() -> RedirectResponse:
    """Redirect top-level /openapi.json to versioned OpenAPI specification."""
    return RedirectResponse(url=f"{settings.API_V1_STR}/openapi.json")


@app.get("/missions", include_in_schema=False)
@app.get("/discovery", include_in_schema=False)
@app.get("/terrain-twin", include_in_schema=False)
@app.get("/terrain-comparison", include_in_schema=False)
async def redirect_frontend_routes(request: Request) -> RedirectResponse:
    """Redirect web workspace route requests to the deployed frontend app."""
    return RedirectResponse(url=f"https://frontend-alpha-azure-30.vercel.app{request.url.path}")
