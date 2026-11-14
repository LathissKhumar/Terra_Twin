"""Analogue discovery route placeholders."""

from fastapi import APIRouter

router = APIRouter(prefix="/discovery", tags=["Discovery"])


@router.get("/jobs")
async def list_discovery_jobs() -> dict[str, str]:
    return {"message": "Analogue discovery jobs endpoint ready"}
