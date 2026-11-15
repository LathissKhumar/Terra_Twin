"""Versioned API router assembling implemented TerraTwin product endpoints."""

from fastapi import APIRouter

from app.api.routes import (
    assessments,
    datasets,
    discovery,
    evidence,
    health,
    missions,
    terrain,
    terrain_twin,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(missions.router)
api_router.include_router(datasets.router)
api_router.include_router(discovery.router)
api_router.include_router(terrain.router)
api_router.include_router(terrain_twin.router)
api_router.include_router(assessments.router)
api_router.include_router(evidence.router)
