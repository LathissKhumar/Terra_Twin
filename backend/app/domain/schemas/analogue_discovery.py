"""Typed configuration and result contracts for analogue discovery."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FeatureName = Literal[
    "slope",
    "local_relief",
    "terrain_roughness",
    "profile_curvature",
    "plan_curvature",
    "topographic_position_index",
    "landform_morphology",
]
CandidateStatus = Literal["eligible", "insufficient_evidence"]


def _default_normalization_floors() -> dict[FeatureName, float]:
    return {
        "slope": 1.0,
        "local_relief": 1.0,
        "terrain_roughness": 0.5,
        "profile_curvature": 1e-5,
        "plan_curvature": 1e-5,
        "topographic_position_index": 1.0,
    }


class MissionExperimentProfile(BaseModel):
    """Versioned, inspectable feature priorities; weights are provisional choices."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    profile_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=30)
    feature_weights: dict[FeatureName, float]
    required_features: list[FeatureName]
    justifications: dict[FeatureName, str]

    @model_validator(mode="after")
    def validate_profile(self) -> MissionExperimentProfile:
        if not self.required_features or len(set(self.required_features)) != len(
            self.required_features
        ):
            raise ValueError("Mission profile requires a nonempty unique feature list")
        if set(self.feature_weights) != set(self.required_features):
            raise ValueError("Each required feature must have exactly one configured weight")
        if set(self.justifications) != set(self.required_features):
            raise ValueError("Each required feature must have a written justification")
        if any(
            not math.isfinite(weight) or weight <= 0 for weight in self.feature_weights.values()
        ):
            raise ValueError("Feature weights must be finite and greater than zero")
        if any(not reason.strip() for reason in self.justifications.values()):
            raise ValueError("Feature weight justifications cannot be empty")
        return self


ROVER_MOBILITY_PROFILE = MissionExperimentProfile(
    profile_id="ROVER_MOBILITY_AND_TERRAIN_NAVIGATION",
    version="1.1.0",
    feature_weights={
        "slope": 0.20,
        "local_relief": 0.18,
        "terrain_roughness": 0.18,
        "profile_curvature": 0.12,
        "plan_curvature": 0.12,
        "topographic_position_index": 0.12,
        "landform_morphology": 0.08,
    },
    required_features=[
        "slope",
        "local_relief",
        "terrain_roughness",
        "profile_curvature",
        "plan_curvature",
        "topographic_position_index",
        "landform_morphology",
    ],
    justifications={
        "slope": "A provisional mobility geometry descriptor; weight is a researcher-set prior.",
        "local_relief": "A provisional local elevation-range descriptor at the declared support.",
        "terrain_roughness": "A provisional elevation-dispersion descriptor, not traction.",
        "profile_curvature": "A provisional along-slope shape descriptor.",
        "plan_curvature": "A provisional cross-slope shape descriptor.",
        "topographic_position_index": "A provisional local-high/low context descriptor.",
        "landform_morphology": "A low-weight relative-position class summary only.",
    },
)


class DiscoveryConfig(BaseModel):
    """Physical search dimensions and explicit evidence/scoring controls."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_width_m: float = Field(default=20_000, gt=0, le=500_000)
    candidate_height_m: float = Field(default=20_000, gt=0, le=500_000)
    candidate_stride_m: float = Field(default=10_000, gt=0, le=500_000)
    selected_features: list[FeatureName] = Field(
        default_factory=lambda: list(ROVER_MOBILITY_PROFILE.required_features)
    )
    minimum_evidence_coverage: float = Field(default=0.8, gt=0, le=1)
    minimum_feature_samples: int = Field(default=20, ge=2, le=1_000_000)
    maximum_candidate_count: int = Field(default=10_000, ge=1, le=1_000_000)
    duplicate_overlap_iou: float = Field(default=0.1, gt=0, le=1)
    bootstrap_replicates: int = Field(default=100, ge=0, le=2_000)
    spatial_bootstrap_block_cells: int = Field(default=3, ge=2, le=101)
    normalization_scale_floor: dict[FeatureName, float] = Field(
        default_factory=_default_normalization_floors
    )
    search_boundary_wgs84: tuple[float, float, float, float] | None = None

    @model_validator(mode="after")
    def validate_config(self) -> DiscoveryConfig:
        if not self.selected_features or len(set(self.selected_features)) != len(
            self.selected_features
        ):
            raise ValueError("Selected features must be a nonempty unique list")
        for value in (
            self.candidate_width_m,
            self.candidate_height_m,
            self.candidate_stride_m,
            self.minimum_evidence_coverage,
        ):
            if not math.isfinite(value):
                raise ValueError("Discovery configuration values must be finite")
        if any(
            not math.isfinite(value) or value <= 0
            for value in self.normalization_scale_floor.values()
        ):
            raise ValueError("Normalization scale floors must be positive finite values")
        boundary = self.search_boundary_wgs84
        if boundary is not None:
            west, south, east, north = boundary
            if (
                not all(math.isfinite(value) for value in boundary)
                or west < -180
                or east > 180
                or south < -90
                or north > 90
                or west >= east
                or south >= north
            ):
                raise ValueError("Search boundary must be ordered WGS84 west,south,east,north")
        return self


class CandidateWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    row_off: int = Field(ge=0)
    col_off: int = Field(ge=0)
    height: int = Field(gt=0)
    width: int = Field(gt=0)
    actual_width_m: float = Field(gt=0)
    actual_height_m: float = Field(gt=0)


class PlanetaryReferenceWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    row_off: int = Field(ge=0)
    col_off: int = Field(ge=0)
    height: int = Field(gt=0)
    width: int = Field(gt=0)
    center_row: float
    center_col: float
    requested_width_m: float = Field(gt=0)
    requested_height_m: float = Field(gt=0)
    actual_width_m: float = Field(gt=0)
    actual_height_m: float = Field(gt=0)


class FeatureComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feature: FeatureName
    method: str
    units: str
    reference_sample_count: int = Field(ge=0)
    candidate_sample_count: int = Field(ge=0)
    reference_coverage: float = Field(ge=0, le=1)
    candidate_coverage: float = Field(ge=0, le=1)
    wasserstein_distance: float | None = Field(default=None, ge=0)
    median_difference: float | None = None
    normalization_scale: float | None = Field(default=None, gt=0)
    normalized_distance: float | None = Field(default=None, ge=0)
    distance_standard_error: float | None = Field(default=None, ge=0)
    reference_median: float | None = None
    candidate_median: float | None = None
    reference_summary: dict[str, float] = Field(default_factory=dict)
    candidate_summary: dict[str, float] = Field(default_factory=dict)
    reference_class_fractions: dict[str, float] = Field(default_factory=dict)
    candidate_class_fractions: dict[str, float] = Field(default_factory=dict)


class CandidateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    window: CandidateWindow
    geographic_boundary_wgs84: list[tuple[float, float]]
    centroid_wgs84: tuple[float, float]
    feature_comparisons: dict[str, FeatureComparison]
    required_features: list[FeatureName]
    available_features: list[FeatureName]
    missing_features: list[FeatureName]
    feature_coverage: dict[str, float]
    planetary_feature_coverage: dict[str, float]
    earth_feature_coverage: dict[str, float]
    evidence_coverage: float = Field(ge=0, le=1)
    status: CandidateStatus
    weighted_distance: float | None = Field(default=None, ge=0)
    weighted_distance_standard_error: float | None = Field(default=None, ge=0)
    ranking: int | None = Field(default=None, ge=1)
    cluster_id: str
    selected_cluster_representative: bool
    source_dataset_ids: dict[str, str]
    source_sha256: dict[str, str]
    processing_configuration_sha256: str
    mission_profile_id: str
    mission_profile_version: str
    scale_bridge_run_id: str
    planetary_analytics_run_id: str
    earth_analytics_run_id: str
    warnings: list[str]


class DiscoveryReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    reproducibility_sha256: str
    engine_version: str
    scale_bridge_run_id: str
    mission_profile: MissionExperimentProfile
    config: DiscoveryConfig
    search_boundary_wgs84: tuple[float, float, float, float]
    planetary_dataset_id: str
    planetary_source_sha256: str
    earth_dataset_id: str
    earth_source_sha256: str
    planetary_analytics_run_id: str
    earth_analytics_run_id: str
    planetary_effective_resolution_m: float | None
    earth_effective_resolution_m: float | None
    planetary_source_product: str
    earth_source_product: str
    # Optional for persisted reports written before surface classifications
    # were added. Missing provenance stays explicitly unavailable.
    planetary_surface_type: str | None = None
    earth_surface_type: str | None = None
    planetary_reference_boundary_body_lon_lat: tuple[float, float, float, float]
    planetary_reference_coordinate_body: str
    planetary_reference_window: PlanetaryReferenceWindow
    uncertainty_method: str
    earth_pixel_width_m: float = Field(gt=0)
    earth_pixel_height_m: float = Field(gt=0)
    planetary_reference_width_m: float = Field(gt=0)
    planetary_reference_height_m: float = Field(gt=0)
    candidate_width_cells: int = Field(gt=0)
    candidate_height_cells: int = Field(gt=0)
    actual_candidate_width_m: float = Field(gt=0)
    actual_candidate_height_m: float = Field(gt=0)
    actual_stride_x_m: float = Field(gt=0)
    actual_stride_y_m: float = Field(gt=0)
    generated_window_count: int = Field(ge=0)
    evaluated_window_count: int = Field(ge=0)
    eligible_candidate_count: int = Field(ge=0)
    ranked_candidate_count: int = Field(ge=0)
    candidates: list[CandidateResult]
    warnings: list[str]
