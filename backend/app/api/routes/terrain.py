"""Terrain analysis route placeholders."""

from fastapi import APIRouter

router = APIRouter(prefix="/terrain", tags=["Terrain"])


@router.get("/analytics")
async def get_terrain_analytics() -> dict[str, str]:
    return {"message": "Terrain analytics endpoint ready"}
