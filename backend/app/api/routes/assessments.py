"""Terrain-to-Test Intelligence assessment route placeholders."""

from fastapi import APIRouter

router = APIRouter(prefix="/assessments", tags=["Assessments"])


@router.get("")
async def list_assessments() -> dict[str, str]:
    return {"message": "Mission transferability assessment endpoint ready"}
