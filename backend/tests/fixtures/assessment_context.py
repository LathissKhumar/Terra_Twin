"""Explicit synthetic model records for isolated deterministic-rule tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import rasterio

from app.core.config import BACKEND_DIR
from app.domain.schemas.analogue_discovery import (
    ROVER_MOBILITY_PROFILE,
    CandidateResult,
    CandidateWindow,
    DiscoveryConfig,
    DiscoveryReport,
    FeatureComparison,
)
from app.domain.schemas.datasets import DatasetManifest
from app.domain.schemas.mission_assessment import MissionAssessmentProfile
from app.domain.schemas.terrain_twin import TerrainTwinMetadata
from app.engines.data_ingestion.ingestion import sha256_file
from app.services.assessment_service import CandidateEvidenceContext

PROFILE_PATH = (
    BACKEND_DIR / "config" / "mission_profiles" / "rover_mobility_and_terrain_navigation_v1.json"
)
PROFILE = MissionAssessmentProfile.model_validate_json(PROFILE_PATH.read_text())
PROFILE_SHA256 = sha256_file(PROFILE_PATH)
FEATURES = PROFILE.required_features
TEST_CANDIDATE_ID = "a" * 24
TEST_RUN_ID = "fixture-run-7"


def build_candidate_and_report(
    *,
    status: str = "insufficient_evidence",
    coverage: float = 0.01,
    sample_count: int = 4,
    missing_features: list[str] | None = None,
    normalized_distances: dict[str, float] | None = None,
) -> tuple[CandidateResult, DiscoveryReport]:
    comparisons = {
        feature: FeatureComparison(
            feature=feature,
            method="test-only Wasserstein distance normalized by test scale",
            units="test units",
            reference_sample_count=sample_count,
            candidate_sample_count=sample_count + 2,
            reference_coverage=coverage,
            candidate_coverage=0.95,
            wasserstein_distance=0.25,
            median_difference=0.1,
            normalization_scale=1.0,
            normalized_distance=(normalized_distances or {}).get(feature, 0.25),
            distance_standard_error=0.02,
            reference_median=2.0,
            candidate_median=2.1,
        )
        for feature in FEATURES
    }
    candidate = CandidateResult.model_construct(
        candidate_id=TEST_CANDIDATE_ID,
        window=CandidateWindow(
            row_off=0,
            col_off=0,
            height=44,
            width=44,
            actual_width_m=20_372.0,
            actual_height_m=20_372.0,
        ),
        geographic_boundary_wgs84=[
            (77.0, 18.0),
            (77.1, 18.0),
            (77.1, 18.1),
            (77.0, 18.1),
            (77.0, 18.0),
        ],
        centroid_wgs84=(77.05, 18.05),
        status=status,
        ranking=None if status == "insufficient_evidence" else 1,
        evidence_coverage=coverage,
        weighted_distance=None if status == "insufficient_evidence" else 0.3,
        weighted_distance_standard_error=None if status == "insufficient_evidence" else 0.04,
        missing_features=(
            list(FEATURES)
            if missing_features is None and status == "insufficient_evidence"
            else missing_features or []
        ),
        required_features=list(FEATURES),
        available_features=list(FEATURES),
        feature_comparisons=comparisons,
        feature_coverage={feature: coverage for feature in FEATURES},
        planetary_feature_coverage={feature: coverage for feature in FEATURES},
        earth_feature_coverage={feature: 0.95 for feature in FEATURES},
        warnings=[],
        cluster_id="fixture-cluster",
        selected_cluster_representative=True,
        source_dataset_ids={"planetary": "1" * 64, "earth": "2" * 64},
        source_sha256={"planetary": "3" * 64, "earth": "4" * 64},
        processing_configuration_sha256="5" * 64,
        mission_profile_id=ROVER_MOBILITY_PROFILE.profile_id,
        mission_profile_version=ROVER_MOBILITY_PROFILE.version,
        scale_bridge_run_id="fixture-bridge",
        planetary_analytics_run_id="fixture-mars-analytics",
        earth_analytics_run_id="fixture-earth-analytics",
    )
    config = DiscoveryConfig(
        selected_features=list(FEATURES),
        minimum_evidence_coverage=0.8,
        minimum_feature_samples=20,
    )
    report = DiscoveryReport.model_construct(
        run_id=TEST_RUN_ID,
        candidates=[candidate],
        config=config,
        mission_profile=ROVER_MOBILITY_PROFILE,
        planetary_dataset_id="1" * 64,
        earth_dataset_id="2" * 64,
        planetary_source_product="Test-only Mars DEM fixture",
        earth_source_product="Test-only Earth DEM fixture",
        planetary_reference_boundary_body_lon_lat=(1.0, 2.0, 3.0, 4.0),
        planetary_reference_coordinate_body="mars",
        planetary_reference_width_m=20_372.0,
        planetary_reference_height_m=20_372.0,
        planetary_effective_resolution_m=None,
        planetary_reference_window=None,
        earth_pixel_width_m=30.0,
        earth_pixel_height_m=30.0,
        generated_window_count=1,
        evaluated_window_count=1,
        eligible_candidate_count=0,
        ranked_candidate_count=0,
        search_boundary_wgs84=(77.0, 18.0, 78.0, 19.0),
        scale_bridge_run_id="fixture-bridge",
        engine_version="test-only",
        reproducibility_sha256="6" * 64,
        uncertainty_method="Synthetic test uncertainty only.",
        planetary_analytics_run_id="fixture-mars-analytics",
        earth_analytics_run_id="fixture-earth-analytics",
        warnings=["Test fixture; not a scientific discovery result."],
    )
    return candidate, report


def build_unvalidated_twin(dataset_id: str = "2" * 64) -> TerrainTwinMetadata:
    return TerrainTwinMetadata.model_construct(
        terrain_twin_id="b" * 24,
        candidate_id=TEST_CANDIDATE_ID,
        discovery_run_id=TEST_RUN_ID,
        source_dataset_id=dataset_id,
        validation_status="unvalidated",
        validation_reason="Test-only missing independent reference.",
        software={"engine": "test-only"},
    )


def _fixture_manifest(path: Path, body: str, dataset_id: str) -> DatasetManifest:
    with rasterio.open(path) as raster:
        bounds = raster.bounds
        width, height = raster.width, raster.height
        res = raster.res
        crs = raster.crs.to_string()
        dtype = raster.dtypes[0]
        nodata = raster.nodata
    return DatasetManifest(
        id=dataset_id,
        target_body=body,
        provider="Documented real-source sample fixture",
        product="Test-only compact DEM window",
        version="fixture sample",
        source_url="https://example.invalid/test-fixture-provenance",
        downloaded_at=datetime(2026, 11, 15, tzinfo=UTC),
        checksum_sha256=sha256_file(path),
        file_size_bytes=path.stat().st_size,
        crs=crs,
        bounds=(bounds.left, bounds.bottom, bounds.right, bounds.top),
        width=width,
        height=height,
        pixel_resolution_x=abs(res[0]),
        pixel_resolution_y=abs(res[1]),
        resolution_unit="degrees" if body == "earth" else "m",
        vertical_units="m",
        vertical_reference="Test fixture reference only",
        nodata=nodata,
        dtype=dtype,
        processing_status="validated",
        license="test fixture terms",
        attribution="Automated test fixture; not product evidence",
        media_type="image/tiff",
    )


def build_passport_context(tmp_path: Path) -> CandidateEvidenceContext:
    fixture_dir = BACKEND_DIR / "tests" / "fixtures" / "data"
    mars_path = fixture_dir / "mola_megt44n000hb_jezero_window.tif"
    earth_path = fixture_dir / "copernicus_glo30_n18_e077_window.tif"
    mars_id, earth_id = sha256_file(mars_path), sha256_file(earth_path)
    mars = _fixture_manifest(mars_path, "mars", mars_id)
    earth = _fixture_manifest(earth_path, "earth", earth_id)
    candidate, report = build_candidate_and_report()
    candidate = CandidateResult.model_construct(
        **{
            **candidate.__dict__,
            "source_dataset_ids": {"planetary": mars_id, "earth": earth_id},
        }
    )
    report = DiscoveryReport.model_construct(
        **{
            **report.__dict__,
            "candidates": [candidate],
            "planetary_dataset_id": mars_id,
            "earth_dataset_id": earth_id,
            "planetary_source_sha256": "7" * 64,
            "earth_source_sha256": "8" * 64,
            "planetary_effective_resolution_m": None,
            "earth_effective_resolution_m": None,
            "actual_candidate_width_m": 20_372.0,
            "actual_candidate_height_m": 20_372.0,
            "candidate_width_cells": 44,
            "candidate_height_cells": 44,
            "actual_stride_x_m": 10_186.0,
            "actual_stride_y_m": 10_186.0,
        }
    )
    report_path = tmp_path / "discovery-report.json"
    report_path.write_text(report.model_dump_json())
    bridge = {
        "run_id": report.scale_bridge_run_id,
        "target_resolution_m": 463.0,
        "target_resolution_basis": "test-only coarse source support",
        "resampling": "test-only aggregation",
        "information_loss": {"planetary": "test fixture", "earth": "test fixture"},
        "actual_support_width_m": 20_372.0,
        "actual_support_height_m": 20_372.0,
        "coverage": {"common_fraction": 0.01},
        "vertical_comparison": "relative terrain only",
        "vertical_normalization": "test-only relative references",
        "warnings": ["Test fixture; not a real processing report."],
    }
    bridge_path = tmp_path / "scale-bridge-report.json"
    bridge_path.write_text(json.dumps(bridge))
    manifest_paths = {"planetary": mars_path, "earth": earth_path}
    manifests = {"planetary": mars, "earth": earth}
    manifest_hashes = {
        "planetary": sha256_file(mars_path),
        "earth": sha256_file(earth_path),
    }
    return CandidateEvidenceContext(
        discovery_report=report,
        discovery_report_path=report_path,
        discovery_report_sha256=sha256_file(report_path),
        candidate=candidate,
        scale_bridge=bridge,
        scale_bridge_report_path=bridge_path,
        scale_bridge_report_sha256=sha256_file(bridge_path),
        manifests=manifests,
        manifest_paths=manifest_paths,
        manifest_sha256=manifest_hashes,
        profile=PROFILE,
        profile_sha256=PROFILE_SHA256,
        terrain_twin=None,
        terrain_twin_metadata_path=None,
        terrain_twin_metadata_sha256=None,
        terrain_mesh_sha256=None,
    )
