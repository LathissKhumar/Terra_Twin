"""Mission profile route placeholders."""

from fastapi import APIRouter

router = APIRouter(prefix="/missions", tags=["Missions"])


@router.get("")
async def list_missions() -> dict[str, str]:
    """List available planetary missions and reference targets."""
    return {"message": "Mission discovery endpoint ready"}
