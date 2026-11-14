"""Only implemented routes are mounted in Phase 1."""

from fastapi import APIRouter

from app.api.routes import datasets, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(datasets.router)
