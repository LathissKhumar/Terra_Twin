"""Explicit configuration and reports for cross-body raster harmonization."""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GeographicCenter(BaseModel):
    """Body-specific longitude/latitude in degrees, interpreted on the source body's datum."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    longitude: float
    latitude: float

    @model_validator(mode="after")
    def validate_coordinate(self) -> GeographicCenter:
        if not -360 <= self.longitude <= 360 or not -90 <= self.latitude <= 90:
            raise ValueError("Center must be a valid longitude/latitude in degrees")
        return self


class SourceGridReport(BaseModel):
    """Input and projected grid properties retained in the run report."""

    dataset_id: str
    target_body: str
    product: str
    source_crs: str
    source_horizontal_units: str
    local_metric_crs: str
    nominal_ground_spacing_x_m: float
    nominal_ground_spacing_y_m: float
    effective_resolution_m: float | None
    vertical_units: str
    vertical_reference: str
    center_longitude_latitude: tuple[float, float]
    source_bounds: tuple[float, float, float, float]
    source_geographic_bounds_lon_lat: tuple[float, float, float, float]
    relative_elevation_reference_m: float


class CoverageReport(BaseModel):
    """Coverage on each output surface and, when grids correspond, paired cells."""

    planetary_valid_cells: int
    earth_valid_cells: int
    planetary_output_cells: int = Field(gt=0)
    output_cells: int
    planetary_valid_area_m2: float = Field(ge=0)
    earth_valid_area_m2: float = Field(ge=0)
    planetary_fraction: float = Field(ge=0, le=1)
    earth_fraction: float = Field(ge=0, le=1)
    common_valid_cells: int | None = Field(default=None, ge=0)
    common_fraction: float | None = Field(default=None, ge=0, le=1)
    common_valid_area_m2: float | None = Field(default=None, ge=0)


class ObservationCountsReport(BaseModel):
    """Optional source-quality mask used for products with ancillary counts."""

    product_id: str
    checksum_sha256: str
    source_topography_id: str
    count_units: str
    zero_count_policy: str
    observed_source_cells: int = Field(ge=0)
    total_source_cells: int = Field(gt=0)
    maximum_count: int = Field(ge=0)


class ScaleBridgeReport(BaseModel):
    """Reproducible scientific decisions and warnings for one paired run."""

    model_config = ConfigDict(extra="forbid")
    run_id: str
    planetary: SourceGridReport
    earth: SourceGridReport
    target_resolution_m: float = Field(gt=0)
    target_resolution_basis: str
    resampling: str
    information_loss: dict[str, str]
    requested_support_width_m: float = Field(gt=0)
    requested_support_height_m: float = Field(gt=0)
    actual_support_width_m: float = Field(gt=0)
    actual_support_height_m: float = Field(gt=0)
    planetary_requested_support_width_m: float = Field(gt=0)
    planetary_requested_support_height_m: float = Field(gt=0)
    planetary_actual_support_width_m: float = Field(gt=0)
    planetary_actual_support_height_m: float = Field(gt=0)
    alignment_description: str
    grid_width: int = Field(gt=0)
    grid_height: int = Field(gt=0)
    planetary_grid_width: int = Field(gt=0)
    planetary_grid_height: int = Field(gt=0)
    minimum_valid_fraction_per_cell: float = Field(gt=0, le=1)
    coverage: CoverageReport
    planetary_observation_counts: ObservationCountsReport | None = None
    vertical_comparison: str = "relative terrain only; absolute elevations not compared"
    output_vertical_units: str = "m"
    vertical_normalization: str
    area_calculation: str
    common_mask_semantics: str
    processing_software: dict[str, str]
    reproducibility_sha256: str
    warnings: list[str]
    artifacts: dict[str, str]
    artifact_sha256: dict[str, str]


class ScaleBridgeConfig(BaseModel):
    """Independent body supports at one shared metric comparison resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    planetary_center: GeographicCenter
    earth_center: GeographicCenter
    support_width_m: float = Field(gt=0, le=500_000)
    support_height_m: float = Field(gt=0, le=500_000)
    planetary_support_width_m: float | None = Field(default=None, gt=0, le=500_000)
    planetary_support_height_m: float | None = Field(default=None, gt=0, le=500_000)
    target_resolution_m: float | None = Field(default=None, gt=0)
    minimum_valid_fraction_per_cell: float = Field(default=0.999, gt=0, le=1)

    @field_validator("target_resolution_m")
    @classmethod
    def finite_resolution(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("Target resolution must be finite")
        return value

    @field_validator(
        "support_width_m",
        "support_height_m",
        "planetary_support_width_m",
        "planetary_support_height_m",
        "minimum_valid_fraction_per_cell",
    )
    @classmethod
    def finite_configuration_values(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("ScaleBridge configuration values must be finite")
        return value

    @property
    def planetary_width_m(self) -> float:
        return self.planetary_support_width_m or self.support_width_m

    @property
    def planetary_height_m(self) -> float:
        return self.planetary_support_height_m or self.support_height_m
