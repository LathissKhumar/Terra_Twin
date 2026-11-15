"""Typed requests and provenance for DEM-derived Terrain Twin artifacts."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TerrainTwinCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    max_vertices: int = Field(default=150_000, ge=1_000, le=250_000)
    chunk_cells: int = Field(default=128, ge=32, le=512)
    vertical_exaggeration: float = Field(default=1.0, gt=0, le=10)
    reference_dataset_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def finite_vertical_scale(self) -> TerrainTwinCreateRequest:
        if not math.isfinite(self.vertical_exaggeration):
            raise ValueError("Vertical exaggeration must be finite")
        return self


class TerrainTwinCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    discovery_run_id: str
    discovery_status: Literal["eligible", "insufficient_evidence"]
    ranking: int | None
    centroid_wgs84: tuple[float, float]
    geographic_boundary_wgs84: list[tuple[float, float]]
    source_dataset_id: str
    source_product: str
    weighted_distance: float | None = None
    weighted_distance_standard_error: float | None = None
    evidence_coverage: float | None = None
    feature_distances: dict[str, float] = Field(default_factory=dict)


class ValidationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mean_absolute_error_m: float
    root_mean_square_error_m: float
    median_absolute_error_m: float
    mean_bias_m: float
    error_percentiles_m: dict[str, float]
    absolute_error_percentiles_m: dict[str, float]
    valid_sample_count: int = Field(ge=1)
    valid_comparison_area_m2: float = Field(ge=0)
    valid_coverage: float = Field(ge=0, le=1)
    resampling: str
    comparison_support_m: float | None = Field(default=None, gt=0)


class TerrainTwinMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    terrain_twin_id: str
    candidate_id: str
    discovery_run_id: str
    discovery_status: Literal["eligible", "insufficient_evidence"]
    ranking: int | None
    source_dataset_id: str
    source_product: str
    source_sha256: str
    geographic_bounds_wgs84: tuple[float, float, float, float]
    candidate_boundary_wgs84: list[tuple[float, float]]
    source_crs: str
    mesh_crs: str
    horizontal_transformation: str
    source_vertical_units: str
    source_vertical_reference: str
    vertical_transformation: str
    vertical_exaggeration: float
    source_raster_resolution: tuple[float, float]
    source_resolution_unit: str
    mesh_resolution_m: tuple[float, float]
    source_dimensions: tuple[int, int]
    candidate_crop_dimensions: tuple[int, int]
    mesh_dimensions: tuple[int, int]
    simplification_stride: int
    max_vertices: int
    actual_vertex_count: int
    chunk_count: int
    source_valid_cell_count: int
    source_nodata_cell_count: int
    source_candidate_exterior_cell_count: int
    mesh_valid_cell_count: int
    mesh_nodata_cell_count: int
    elevation_range_m: tuple[float, float]
    validation_status: Literal["validated", "unvalidated"]
    validation_reason: str | None
    reference_dataset_id: str | None
    reference_sha256: str | None
    validation_metrics: ValidationMetrics | None
    artifacts: dict[str, str]
    warnings: list[str]
    software: dict[str, str]
