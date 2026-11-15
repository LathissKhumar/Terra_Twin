"""Candidate-scoped mission transferability assessments."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.domain.schemas.mission_assessment import MissionAssessment
from app.services.assessment_service import get_candidate_assessment

router = APIRouter(prefix="/candidates", tags=["Assessments"])
_DEFAULT_PROFILE = "ROVER_MOBILITY_AND_TERRAIN_NAVIGATION"


@router.get("/{candidate_id}/assessment", response_model=MissionAssessment)
def get_assessment(
    candidate_id: str,
    mission_profile_id: Annotated[str, Query(min_length=1, max_length=100)] = _DEFAULT_PROFILE,
) -> MissionAssessment:
    """Return a rule-based assessment with source-linked measurements and gaps."""
    return get_candidate_assessment(candidate_id, mission_profile_id)
