"""Provenance contract for ancillary per-cell observation-count rasters."""

from __future__ import annotations

import math
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ObservationCountsManifest(BaseModel):
    """A co-registered count raster; zero means no observation, not NoData."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f]{64}$")
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_topography_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str
    product: str
    product_id: str
    source_url: str
    label_source_url: str
    downloaded_at: datetime
    file_size_bytes: int = Field(gt=0)
    crs: str
    bounds: tuple[float, float, float, float]
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    pixel_resolution_x: float = Field(gt=0)
    pixel_resolution_y: float = Field(gt=0)
    dtype: str
    count_units: str
    zero_count_means_unobserved: bool
    total_cells: int = Field(gt=0)
    observed_cells: int = Field(ge=0)
    maximum_count: int = Field(ge=0)
    label_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attribution: str

    @field_validator("bounds")
    @classmethod
    def finite_bounds(
        cls, value: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        if not all(math.isfinite(part) for part in value):
            raise ValueError("Observation raster bounds must be finite")
        if value[0] >= value[2] or value[1] >= value[3]:
            raise ValueError("Observation raster bounds must have positive area")
        return value

    @model_validator(mode="after")
    def validate_provenance(self) -> ObservationCountsManifest:
        if self.id != self.checksum_sha256:
            raise ValueError("Observation manifest ID must match the raster checksum")
        if self.observed_cells > self.total_cells:
            raise ValueError("Observed-cell count cannot exceed total cells")
        if not self.zero_count_means_unobserved:
            raise ValueError("This count manifest requires zero to mean unobserved")
        return self
