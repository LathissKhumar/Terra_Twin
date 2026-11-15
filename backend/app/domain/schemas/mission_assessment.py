"""Versioned deterministic mission assessment contracts."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.schemas.analogue_discovery import FeatureName

AssessmentCategory = Literal[
    "POTENTIALLY_TRANSFERABLE",
    "REQUIRES_ADDITIONAL_EVIDENCE",
    "CANNOT_BE_REPRODUCED_BY_THE_EARTH_SITE_ALONE",
]
EvidenceStatus = Literal[
    "SUPPORTED_WITH_LIMITS",
    "INSUFFICIENT_EVIDENCE",
    "ADDITIONAL_EVIDENCE_REQUIRED",
    "PROFILE_RULE_ONLY",
    "UNVALIDATED",
    "UNAVAILABLE",
]


class MissionAssessmentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=30)
    experiment_name: str
    profile_status: Literal["provisional", "reviewed"]
    weights: dict[FeatureName, float]
    weight_justifications: dict[FeatureName, str]
    required_features: list[FeatureName]
    optional_evidence: list[str]
    additional_evidence_required: list[str]
    not_reproducible_by_earth_site_alone: list[str]
    assessment_rules: dict[str, bool | float | int | str]
    known_limitations: list[str]

    @model_validator(mode="after")
    def validate_weights_and_features(self) -> MissionAssessmentProfile:
        if not self.required_features or len(set(self.required_features)) != len(
            self.required_features
        ):
            raise ValueError("Mission profile requires a unique nonempty feature set")
        if set(self.weights) != set(self.required_features):
            raise ValueError("Every required feature must have one configured weight")
        if set(self.weight_justifications) != set(self.required_features):
            raise ValueError("Every feature weight requires a justification")
        if any(not math.isfinite(weight) or weight <= 0 for weight in self.weights.values()):
            raise ValueError("Mission profile weights must be positive finite values")
        if not math.isclose(sum(self.weights.values()), 1, abs_tol=1e-9):
            raise ValueError("Mission profile weights must sum to one")
        return self


class AssessmentEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["discovery_feature", "discovery_candidate", "terrain_twin", "profile_rule"]
    source_record_id: str
    source_dataset_id: str | None = None
    feature: FeatureName | None = None
    source_field: str
    comparison_method: str
    measurement: dict[str, bool | float | int | str | None] = Field(default_factory=dict)


class AssessmentConclusion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conclusion_id: str
    category: AssessmentCategory
    conclusion: str
    evidence_status: EvidenceStatus
    evidence_interpretation: str
    evidence: list[AssessmentEvidenceReference]
    missing_information: list[str]
    limitations: list[str]


class MissionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_schema_version: Literal["1.0.0"]
    assessment_id: str
    candidate_id: str
    discovery_run_id: str
    discovery_status: Literal["eligible", "insufficient_evidence"]
    ranking: int | None
    mission_profile_id: str
    mission_profile_version: str
    mission_experiment: str
    overall_evidence_status: EvidenceStatus
    evidence_coverage: float = Field(ge=0, le=1)
    minimum_required_coverage: float = Field(ge=0, le=1)
    minimum_required_samples: int = Field(ge=1)
    weighted_distance: float | None = Field(default=None, ge=0)
    weighted_distance_standard_error: float | None = Field(default=None, ge=0)
    terrain_twin_validation_status: Literal["validated", "unvalidated", "unavailable"]
    conclusions: list[AssessmentConclusion]
    missing_evidence: list[str]
    limitations: list[str]
    assessment_profile_sha256: str
    source_discovery_report_sha256: str
    uncertainty_method: str
