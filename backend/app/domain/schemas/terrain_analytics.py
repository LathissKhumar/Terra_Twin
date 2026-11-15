"""Configuration and numerical report contracts for terrain analytics."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TerrainAnalyticsConfig(BaseModel):
    """Focal-analysis radius and the minimum valid-data fraction per window."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    neighborhood_radius_m: float = Field(default=463.0, gt=0, le=25_000)
    minimum_neighborhood_valid_fraction: float = Field(default=0.8, ge=0.5, le=1.0)
    landform_standardization_scale_m: float | None = Field(default=None, gt=0)
    landform_morphology_enabled: bool = True
    histogram_bins: int = Field(default=12, ge=4, le=64)

    @field_validator(
        "neighborhood_radius_m",
        "minimum_neighborhood_valid_fraction",
        "landform_standardization_scale_m",
    )
    @classmethod
    def finite_values(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("Terrain-analysis configuration values must be finite")
        return value


class HistogramSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bin_edges: list[float]
    counts: list[int]


class NumericFeatureSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valid_sample_count: int = Field(ge=0)
    mean: float | None = None
    median: float | None = None
    standard_deviation: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    percentile_05: float | None = None
    percentile_25: float | None = None
    percentile_75: float | None = None
    percentile_95: float | None = None
    histogram: HistogramSummary


class CategoricalFeatureSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valid_sample_count: int = Field(ge=0)
    category_counts: dict[str, int]


class FeatureMapReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    algorithm: str
    units: str
    raster_file: str
    raster_sha256: str
    valid_sample_count: int = Field(ge=0)
    input_valid_sample_count: int = Field(ge=0)
    coverage_of_input_valid: float = Field(ge=0, le=1)
    coverage_of_raster: float = Field(ge=0, le=1)
    window_cells: tuple[int, int] | None = None
    window_support_m: tuple[float, float] | None = None
    edge_policy: str
    nodata_policy: str
    aggregation: str
    normalization_scale_m: float | None = None
    summary: NumericFeatureSummary | CategoricalFeatureSummary
    categories: dict[str, int] | None = None


class TerrainAnalyticsReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    reproducibility_sha256: str
    source_dataset_id: str
    source_raster_sha256: str
    target_body: Literal["mars", "moon", "earth"]
    source_product: str
    source_surface_type: str
    crs: str
    horizontal_units: str
    vertical_units: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    pixel_width_m: float = Field(gt=0)
    pixel_height_m: float = Field(gt=0)
    source_effective_resolution_m: float | None = Field(default=None, gt=0)
    raster_cell_count: int = Field(gt=0)
    input_valid_cell_count: int = Field(ge=0)
    input_valid_fraction: float = Field(ge=0, le=1)
    config: TerrainAnalyticsConfig
    features: dict[str, FeatureMapReport]
    processing_software: dict[str, str]
    warnings: list[str]


class TerrainAnalyticsResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    report: TerrainAnalyticsReport
    feature_paths: dict[str, str]
