"""Public requests and durable status records for bounded discovery runs."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.schemas.scale_bridge import GeographicCenter

JobState = Literal["queued", "running", "succeeded", "failed", "interrupted"]


class DiscoveryJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    planetary_dataset_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    earth_dataset_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    planetary_center: GeographicCenter
    earth_center: GeographicCenter
    support_width_m: float = Field(default=50_000, ge=10_000, le=250_000)
    support_height_m: float = Field(default=50_000, ge=10_000, le=250_000)
    planetary_reference_width_m: float | None = Field(default=None, ge=1_000, le=250_000)
    planetary_reference_height_m: float | None = Field(default=None, ge=1_000, le=250_000)
    target_resolution_m: float | None = Field(default=None, gt=0, le=10_000)
    candidate_width_m: float = Field(default=20_000, gt=0, le=100_000)
    candidate_height_m: float = Field(default=20_000, gt=0, le=100_000)
    candidate_stride_m: float = Field(default=10_000, gt=0, le=100_000)
    minimum_evidence_coverage: float = Field(default=0.8, gt=0, le=1)
    minimum_feature_samples: int = Field(default=20, ge=2, le=100_000)
    bootstrap_replicates: int = Field(default=30, ge=0, le=500)
    maximum_candidate_count: int = Field(default=500, ge=1, le=5_000)
    minimum_valid_fraction_per_cell: float = Field(default=0.999, gt=0, le=1)
    mission_profile_id: Literal["ROVER_MOBILITY_AND_TERRAIN_NAVIGATION"] = (
        "ROVER_MOBILITY_AND_TERRAIN_NAVIGATION"
    )

    @model_validator(mode="after")
    def validate_physical_support(self) -> DiscoveryJobRequest:
        numbers = (
            self.support_width_m,
            self.support_height_m,
            self.candidate_width_m,
            self.candidate_height_m,
            self.candidate_stride_m,
            self.minimum_evidence_coverage,
            self.minimum_valid_fraction_per_cell,
        )
        if not all(math.isfinite(number) for number in numbers):
            raise ValueError("Job dimensions and thresholds must be finite")
        if self.candidate_width_m > self.support_width_m:
            raise ValueError("Candidate width cannot exceed comparison support width")
        if self.candidate_height_m > self.support_height_m:
            raise ValueError("Candidate height cannot exceed comparison support height")
        if (
            self.planetary_reference_width_m is not None
            and self.candidate_width_m > self.planetary_reference_width_m
        ):
            raise ValueError("Candidate width cannot exceed the planetary reference support")
        if (
            self.planetary_reference_height_m is not None
            and self.candidate_height_m > self.planetary_reference_height_m
        ):
            raise ValueError("Candidate height cannot exceed the planetary reference support")
        return self


class DiscoveryJobStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    request_fingerprint: str
    status: JobState
    stage: str
    progress_percent: int = Field(ge=0, le=100)
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result_run_id: str | None
    failure_code: str | None
    failure_message: str | None
    reused_existing_job: bool = False


class DiscoveryJobPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DiscoveryJobStatus]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
