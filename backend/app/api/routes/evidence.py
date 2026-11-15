"""Versioned Analogue Evidence Passport and reproducible exports."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.domain.schemas.evidence_passport import AnalogueEvidencePassport
from app.services.evidence_pdf import render_passport_pdf
from app.services.evidence_service import get_evidence_passport

router = APIRouter(prefix="/candidates", tags=["Evidence Passports"])
_DEFAULT_PROFILE = "ROVER_MOBILITY_AND_TERRAIN_NAVIGATION"


@router.get("/{candidate_id}/evidence-passport", response_model=AnalogueEvidencePassport)
def get_passport(
    candidate_id: str,
    mission_profile_id: Annotated[str, Query(min_length=1, max_length=100)] = _DEFAULT_PROFILE,
) -> AnalogueEvidencePassport:
    """Build the canonical structured passport from persisted scientific outputs."""
    return get_evidence_passport(candidate_id, mission_profile_id)


@router.get("/{candidate_id}/evidence-passport/export")
def export_passport(
    candidate_id: str,
    format: Literal["json", "pdf"] = "json",
    mission_profile_id: Annotated[str, Query(min_length=1, max_length=100)] = _DEFAULT_PROFILE,
) -> Response:
    """Export the same canonical passport as JSON or readable PDF."""
    passport = get_evidence_passport(candidate_id, mission_profile_id)
    if format == "pdf":
        pdf = render_passport_pdf(passport)
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    'attachment; filename="terratwin-evidence-'
                    f'{passport.candidate.candidate_id}.pdf"'
                ),
                "Cache-Control": "no-store",
            },
        )
    return Response(
        content=passport.model_dump_json(indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="terratwin-evidence-{candidate_id}.json"',
            "Cache-Control": "no-store",
        },
    )
