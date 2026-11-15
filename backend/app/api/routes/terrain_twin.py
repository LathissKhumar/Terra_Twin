"""Candidate-scoped Terrain Twin creation and artifact delivery."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

import rasterio
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from rasterio.warp import transform_geom

from app.core.config import settings
from app.domain.schemas.datasets import DatasetManifest
from app.domain.schemas.terrain_twin import (
    TerrainTwinCandidate,
    TerrainTwinCreateRequest,
    TerrainTwinMetadata,
)
from app.engines.data_ingestion.ingestion import sha256_file
from app.engines.terrain_twin.engine import create_terrain_twin, terrain_twin_identifier
from app.services.discovery_results import report_for_candidate

router = APIRouter(prefix="/terrain-twins", tags=["Terrain Twins"])
_CANDIDATE_ID = re.compile(r"^[0-9a-f]{24}$")
_TWIN_ID = re.compile(r"^[0-9a-f]{24}$")
_ARTIFACT_FILES: dict[str, tuple[str, str]] = {
    "mesh": ("terrain.glb", "model/gltf-binary"),
    "elevation-map": ("elevation.png", "image/png"),
    "slope-map": ("slope.png", "image/png"),
}


def _latest_discovery_report() -> tuple[Path, dict[str, object]]:
    report_root = settings.results_dir / "analogue_discovery"
    reports = list(report_root.glob("*/report.json"))
    if not reports:
        raise HTTPException(status_code=503, detail="No completed discovery report is available")
    for report_path in sorted(reports, key=lambda path: path.stat().st_mtime_ns, reverse=True):
        try:
            payload = json.loads(report_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        if not isinstance(candidates, list):
            continue
        earth_ids = {
            str(source_ids["earth"])
            for candidate in candidates
            if isinstance(candidate, dict)
            and isinstance((source_ids := candidate.get("source_dataset_ids")), dict)
            and isinstance(source_ids.get("earth"), str)
        }
        if len(earth_ids) != 1:
            continue
        try:
            manifest, _ = _manifest_and_raster(earth_ids.pop())
        except HTTPException:
            continue
        if manifest.product_metadata.get("surface_type") != "bare_earth_dtm":
            continue
        return report_path, payload
    raise HTTPException(
        status_code=503,
        detail="No discovery report with a verified bare-earth Earth DEM is available",
    )


def _candidate_from_report(candidate_id: str) -> tuple[TerrainTwinCandidate, dict[str, object]]:
    _, report = report_for_candidate(candidate_id)
    candidates = report.get("candidates")
    if not isinstance(candidates, list):
        raise HTTPException(status_code=503, detail="Discovery report has no candidate records")
    for raw_candidate in candidates:
        if not isinstance(raw_candidate, dict) or raw_candidate.get("candidate_id") != candidate_id:
            continue
        source_ids = raw_candidate.get("source_dataset_ids")
        if not isinstance(source_ids, dict) or not isinstance(source_ids.get("earth"), str):
            raise HTTPException(status_code=503, detail="Candidate has no Earth source reference")
        try:
            result = TerrainTwinCandidate(
                candidate_id=candidate_id,
                discovery_run_id=str(report["run_id"]),
                discovery_status=raw_candidate["status"],
                ranking=raw_candidate.get("ranking"),
                centroid_wgs84=raw_candidate["centroid_wgs84"],
                geographic_boundary_wgs84=raw_candidate["geographic_boundary_wgs84"],
                source_dataset_id=source_ids["earth"],
                source_product=str(report["earth_source_product"]),
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="Candidate provenance is invalid") from exc
        return result, report
    raise HTTPException(
        status_code=404, detail="Candidate is not present in completed discovery results"
    )


def _manifest_and_raster(dataset_id: str) -> tuple[DatasetManifest, Path]:
    if not re.fullmatch(r"[0-9a-f]{64}", dataset_id):
        raise HTTPException(status_code=404, detail="Dataset was not found")
    manifests = list(settings.manifests_dir.rglob(f"{dataset_id}.json"))
    if len(manifests) != 1:
        raise HTTPException(status_code=404, detail="Dataset manifest was not found")
    try:
        manifest = DatasetManifest.model_validate_json(manifests[0].read_text())
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Dataset manifest is invalid") from exc
    if manifest.id != dataset_id or manifest.target_body != "earth":
        raise HTTPException(status_code=404, detail="Earth dataset was not found")
    raw_directory = (settings.raw_data_dir / "earth").resolve()
    matches = [
        path.resolve()
        for suffix in (".tif", ".tiff", ".img", ".hgt", ".jp2")
        for path in raw_directory.glob(f"{dataset_id}{suffix}")
    ]
    matches = [path for path in matches if path.is_relative_to(raw_directory) and path.is_file()]
    if len(matches) != 1:
        raise HTTPException(status_code=404, detail="Immutable Earth source raster is unavailable")
    if sha256_file(matches[0]) != manifest.checksum_sha256:
        raise HTTPException(
            status_code=503, detail="Source raster checksum does not match manifest"
        )
    return manifest, matches[0]


@router.get("/candidates", response_model=list[TerrainTwinCandidate])
def list_terrain_twin_candidates() -> list[TerrainTwinCandidate]:
    """List ranked discovery candidates whose full polygons are covered by their source DEM."""
    _, report = _latest_discovery_report()
    run_id = str(report.get("run_id", ""))
    earth_product = str(report.get("earth_source_product", ""))
    results: list[TerrainTwinCandidate] = []
    candidates = report.get("candidates", [])
    if not isinstance(candidates, list):
        return results
    earth_ids = {
        str(source_ids["earth"])
        for candidate in candidates
        if isinstance(candidate, dict)
        and isinstance((source_ids := candidate.get("source_dataset_ids")), dict)
        and isinstance(source_ids.get("earth"), str)
    }
    if len(earth_ids) != 1:
        return results
    try:
        _, source_path = _manifest_and_raster(earth_ids.pop())
        with rasterio.open(source_path) as source:
            source_bounds = source.bounds
            source_crs = source.crs
    except (HTTPException, OSError):
        return results
    supported: list[tuple[int, TerrainTwinCandidate]] = []
    for raw_candidate in candidates:
        if not isinstance(raw_candidate, dict):
            continue
        source_ids = raw_candidate.get("source_dataset_ids")
        if not isinstance(source_ids, dict) or not isinstance(source_ids.get("earth"), str):
            continue
        boundary = raw_candidate.get("geographic_boundary_wgs84")
        if not isinstance(boundary, list):
            continue
        try:
            projected = transform_geom(
                "EPSG:4326",
                source_crs,
                {"type": "Polygon", "coordinates": [boundary]},
                precision=12,
            )
            ring = projected["coordinates"][0]
            bounds = (
                min(point[0] for point in ring),
                min(point[1] for point in ring),
                max(point[0] for point in ring),
                max(point[1] for point in ring),
            )
            if (
                bounds[0] < source_bounds.left
                or bounds[1] < source_bounds.bottom
                or bounds[2] > source_bounds.right
                or bounds[3] > source_bounds.top
            ):
                continue
        except (TypeError, ValueError, IndexError):
            continue
        try:
            supported.append(
                (
                    int(raw_candidate["ranking"] or 2**31 - 1),
                    TerrainTwinCandidate(
                        candidate_id=raw_candidate["candidate_id"],
                        discovery_run_id=run_id,
                        discovery_status=raw_candidate["status"],
                        ranking=raw_candidate.get("ranking"),
                        centroid_wgs84=raw_candidate["centroid_wgs84"],
                        geographic_boundary_wgs84=raw_candidate["geographic_boundary_wgs84"],
                        source_dataset_id=source_ids["earth"],
                        source_product=earth_product,
                        weighted_distance=raw_candidate.get("weighted_distance"),
                        weighted_distance_standard_error=raw_candidate.get(
                            "weighted_distance_standard_error"
                        ),
                        evidence_coverage=raw_candidate.get("evidence_coverage"),
                        feature_distances={
                            str(name): float(feature["normalized_distance"])
                            for name, feature in raw_candidate.get(
                                "feature_comparisons", {}
                            ).items()
                            if isinstance(feature, dict)
                            and isinstance(feature.get("normalized_distance"), (int, float))
                        },
                    ),
                )
            )
        except (KeyError, ValueError):
            continue
    return [candidate for _, candidate in sorted(supported, key=lambda item: item[0])]


@router.post(
    "/candidates/{candidate_id}",
    response_model=TerrainTwinMetadata,
    status_code=status.HTTP_201_CREATED,
)
def create_candidate_terrain_twin(
    candidate_id: str, request: TerrainTwinCreateRequest
) -> TerrainTwinMetadata:
    """Build from a report-selected candidate; paths are resolved only under data/."""
    candidate, _ = _candidate_from_report(candidate_id)
    source_manifest, source_path = _manifest_and_raster(candidate.source_dataset_id)
    reference_manifest: DatasetManifest | None = None
    reference_path: Path | None = None
    if request.reference_dataset_id is not None:
        reference_manifest, reference_path = _manifest_and_raster(request.reference_dataset_id)
    twin_id = terrain_twin_identifier(
        candidate.candidate_id,
        source_manifest.checksum_sha256,
        max_vertices=request.max_vertices,
        chunk_cells=request.chunk_cells,
        vertical_exaggeration=request.vertical_exaggeration,
        reference_sha256=reference_manifest.checksum_sha256 if reference_manifest else None,
    )
    output_root = (settings.derived_data_dir / "terrain_twins").resolve()
    output_directory = (output_root / twin_id).resolve()
    if not output_directory.is_relative_to(output_root):
        raise HTTPException(status_code=400, detail="Invalid terrain twin output identifier")
    metadata_path = output_directory / "metadata.json"
    if metadata_path.is_file():
        try:
            return TerrainTwinMetadata.model_validate_json(metadata_path.read_text())
        except (OSError, ValueError):
            raise HTTPException(
                status_code=503, detail="Stored terrain twin metadata is invalid"
            ) from None
    try:
        return create_terrain_twin(
            candidate=candidate,
            source_path=source_path,
            source_manifest=source_manifest,
            output_directory=output_directory,
            max_vertices=request.max_vertices,
            chunk_cells=request.chunk_cells,
            vertical_exaggeration=request.vertical_exaggeration,
            reference_path=reference_path,
            reference_manifest=reference_manifest,
            artifact_base_url=f"{settings.API_V1_STR}/terrain-twins/{twin_id}",
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/candidates/{candidate_id}/existing",
    response_model=TerrainTwinMetadata,
)
def get_existing_candidate_terrain_twin(
    candidate_id: str,
    reference_dataset_id: str | None = None,
) -> TerrainTwinMetadata:
    """Return a completed matching mesh without starting reconstruction work."""
    candidate, _ = _candidate_from_report(candidate_id)
    if reference_dataset_id is not None and not re.fullmatch(r"[0-9a-f]{64}", reference_dataset_id):
        raise HTTPException(status_code=422, detail="Invalid reference dataset identifier")
    root = (settings.derived_data_dir / "terrain_twins").resolve()
    for metadata_path in root.glob("*/metadata.json"):
        try:
            metadata = TerrainTwinMetadata.model_validate_json(metadata_path.read_text())
        except (OSError, ValueError):
            continue
        if (
            metadata.candidate_id == candidate_id
            and metadata.discovery_run_id == candidate.discovery_run_id
            and metadata.source_dataset_id == candidate.source_dataset_id
            and metadata.reference_dataset_id == reference_dataset_id
        ):
            return metadata
    raise HTTPException(status_code=404, detail="No completed matching terrain twin exists")


@router.get("/{terrain_twin_id}", response_model=TerrainTwinMetadata)
def get_terrain_twin(terrain_twin_id: str) -> TerrainTwinMetadata:
    if not _TWIN_ID.fullmatch(terrain_twin_id):
        raise HTTPException(status_code=404, detail="Terrain twin was not found")
    root = (settings.derived_data_dir / "terrain_twins").resolve()
    directory = (root / terrain_twin_id).resolve()
    if not directory.is_relative_to(root):
        raise HTTPException(status_code=404, detail="Terrain twin was not found")
    metadata_path = directory / "metadata.json"
    if not metadata_path.is_file():
        raise HTTPException(status_code=404, detail="Terrain twin was not found")
    try:
        return TerrainTwinMetadata.model_validate_json(metadata_path.read_text())
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Terrain twin metadata is invalid") from exc


@router.get("/{terrain_twin_id}/artifacts/{artifact_name}")
def get_terrain_twin_artifact(
    terrain_twin_id: str,
    artifact_name: Literal["mesh", "elevation-map", "slope-map", "error-map", "valid-mask"],
) -> FileResponse:
    if not _TWIN_ID.fullmatch(terrain_twin_id):
        raise HTTPException(status_code=404, detail="Terrain twin was not found")
    root = (settings.derived_data_dir / "terrain_twins").resolve()
    directory = (root / terrain_twin_id).resolve()
    if not directory.is_relative_to(root):
        raise HTTPException(status_code=404, detail="Terrain twin was not found")
    mapping = {
        **_ARTIFACT_FILES,
        "error-map": (
            "elevation_error.png"
            if (directory / "elevation_error.png").is_file()
            else "error_map_unavailable.svg",
            "image/png" if (directory / "elevation_error.png").is_file() else "image/svg+xml",
        ),
        "valid-mask": (
            "valid_comparison_mask.png"
            if (directory / "valid_comparison_mask.png").is_file()
            else "valid_comparison_mask_unavailable.svg",
            "image/png" if (directory / "valid_comparison_mask.png").is_file() else "image/svg+xml",
        ),
    }
    file_name, media_type = mapping[artifact_name]
    target = directory / file_name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Terrain twin artifact was not found")
    return FileResponse(
        target, media_type=media_type, filename=file_name if artifact_name == "mesh" else None
    )
