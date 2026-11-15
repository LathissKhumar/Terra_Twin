"""Versioned, source-linked Analogue Evidence Passport contract."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.schemas.analogue_discovery import (
    DiscoveryConfig,
    FeatureComparison,
    FeatureName,
)
from app.domain.schemas.mission_assessment import MissionAssessment, MissionAssessmentProfile
from app.domain.schemas.terrain_twin import TerrainTwinMetadata


class PassportCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    discovery_run_id: str
    discovery_status: Literal["eligible", "insufficient_evidence"]
    ranking: int | None
    centroid_wgs84: tuple[float, float]
    geographic_boundary_wgs84: list[tuple[float, float]]
    evidence_coverage: float = Field(ge=0, le=1)


class PassportPlanetaryReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Literal["mars", "moon"]
    product: str
    dataset_id: str
    reference_boundary_body_lon_lat: tuple[float, float, float, float]
    coordinate_body: str
    width_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    effective_resolution_m: float | None
    effective_resolution_status: Literal["reported", "unavailable"]


class PassportDatasetSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    target_body: Literal["mars", "moon", "earth"]
    provider: str
    product: str
    version: str | None
    source_url: str | None
    downloaded_at: datetime
    raw_checksum_sha256: str
    manifest_checksum_sha256: str
    discovery_processing_checksum_sha256: str
    file_size_bytes: int = Field(gt=0)
    crs: str
    bounds: tuple[float, float, float, float]
    dimensions: tuple[int, int]
    pixel_resolution: tuple[float, float]
    resolution_unit: str
    vertical_units: str
    vertical_reference: str
    nodata: float | None
    license: str | None
    attribution: str
    processing_status: Literal["validated"]


class FeatureAssessmentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: FeatureName
    evidence_status: Literal["SUPPORTED_WITH_LIMITS", "INSUFFICIENT_EVIDENCE"]
    interpretation: str
    comparison: FeatureComparison
    dataset_ids: dict[Literal["planetary", "earth"], str]
    source_discovery_run_id: str


class PassportWeightedDistance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float | None = Field(default=None, ge=0)
    standard_error: float | None = Field(default=None, ge=0)
    interpretation: str
    method: str


class PassportCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: float = Field(ge=0, le=1)
    required_features: list[FeatureName]
    available_features: list[FeatureName]
    missing_features: list[FeatureName]
    by_feature: dict[FeatureName, float]
    planetary_by_feature: dict[FeatureName, float]
    earth_by_feature: dict[FeatureName, float]
    minimum_required_coverage: float = Field(ge=0, le=1)
    minimum_required_samples_per_surface: int = Field(ge=1)


class PassportUncertainty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str
    feature_distance_standard_errors: dict[FeatureName, float | None]
    instrument_or_dem_measurement_uncertainty: Literal["reported", "unavailable"]
    interpretation: str


class PassportScaleBridge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    target_resolution_m: float
    target_resolution_basis: str
    resampling: str
    information_loss: dict[Literal["planetary", "earth"], str]
    actual_support_width_m: float
    actual_support_height_m: float
    coverage: dict[str, float | None]
    vertical_comparison_status: str
    vertical_normalization: str


class PassportProcessing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discovery_engine_version: str
    discovery_configuration: DiscoveryConfig
    discovery_processing_configuration_sha256: str
    scale_bridge: PassportScaleBridge
    terrain_analytics_run_ids: dict[Literal["planetary", "earth"], str]
    profile_configuration_sha256: str
    terrain_twin_engine_version: str | None


class PassportProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discovery_report_sha256: str
    scale_bridge_report_sha256: str
    dataset_manifest_sha256: dict[str, str]
    terrain_twin_metadata_sha256: str | None
    terrain_mesh_sha256: str | None
    reproducibility_inputs: list[str]


class AnalogueEvidencePassport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passport_schema_version: Literal["1.0.0"]
    passport_id: str
    created_at_utc: datetime
    reproducibility_sha256: str
    candidate: PassportCandidate
    planetary_reference: PassportPlanetaryReference
    mission_profile: MissionAssessmentProfile
    source_datasets: list[PassportDatasetSource]
    feature_evidence: dict[FeatureName, FeatureAssessmentEvidence]
    weighted_distance: PassportWeightedDistance
    evidence_coverage: PassportCoverage
    uncertainty: PassportUncertainty
    terrain_twin: TerrainTwinMetadata | None
    terrain_twin_mesh_sha256: str | None
    terrain_twin_validation_status: Literal["validated", "unvalidated", "unavailable"]
    assessment: MissionAssessment
    missing_evidence: list[str]
    limitations: list[str]
    processing: PassportProcessing
    provenance: PassportProvenance
