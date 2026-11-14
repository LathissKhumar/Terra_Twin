"""Terrain Twin 3D reconstruction route placeholders."""

from fastapi import APIRouter

router = APIRouter(prefix="/terrain-twins", tags=["Terrain Twins"])


@router.get("")
async def list_terrain_twins() -> dict[str, str]:
    return {"message": "Terrain twin 3D meshes endpoint ready"}
