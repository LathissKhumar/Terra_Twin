"""Validated provenance manifest for ingested elevation sources."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DatasetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_body: Literal["mars", "moon", "earth"]
    provider: str
    product: str
    version: str | None = None
    source_url: str | None = None
    downloaded_at: datetime
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_size_bytes: int = Field(gt=0)
    crs: str
    bounds: tuple[float, float, float, float]
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    pixel_resolution_x: float = Field(gt=0)
    pixel_resolution_y: float = Field(gt=0)
    resolution_unit: str
    vertical_units: str
    vertical_reference: str
    nodata: float | int | None
    dtype: str
    processing_status: Literal["validated"]
    license: str | None = None
    attribution: str
    media_type: str
    product_metadata: dict[str, str | int | float | None] = Field(default_factory=dict)

    @field_validator("bounds")
    @classmethod
    def validate_bounds(
        cls, value: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        if not all(math.isfinite(item) for item in value):
            raise ValueError("Raster bounds must be finite")
        if value[0] >= value[2] or value[1] >= value[3]:
            raise ValueError("Raster bounds must have positive area")
        return value

    @model_validator(mode="after")
    def validate_nodata(self) -> DatasetManifest:
        if self.nodata is not None and not math.isfinite(float(self.nodata)):
            raise ValueError("NoData must be finite or explicitly unavailable")
        return self
