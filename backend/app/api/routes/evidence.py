"""Analogue Evidence Passport route placeholders."""

from fastapi import APIRouter

router = APIRouter(prefix="/evidence", tags=["Evidence"])


@router.get("/passports")
async def list_evidence_passports() -> dict[str, str]:
    return {"message": "Analogue evidence passports endpoint ready"}
