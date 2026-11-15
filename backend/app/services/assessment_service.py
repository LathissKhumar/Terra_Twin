"""Resolve exact, validated processing records for a candidate assessment."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.core.config import BACKEND_DIR, settings
from app.domain.schemas.analogue_discovery import CandidateResult, DiscoveryReport
from app.domain.schemas.datasets import DatasetManifest
from app.domain.schemas.mission_assessment import MissionAssessment, MissionAssessmentProfile
from app.domain.schemas.terrain_twin import TerrainTwinMetadata
from app.engines.data_ingestion.ingestion import sha256_file
from app.engines.mission_evaluation.assessment import assess_candidate
from app.services.discovery_results import report_for_candidate

_CANDIDATE_ID = re.compile(r"^[0-9a-f]{24}$")
_DATASET_ID = re.compile(r"^[0-9a-f]{64}$")
_TWIN_ID = re.compile(r"^[0-9a-f]{24}$")
MISSION_PROFILE_PATH = (
    BACKEND_DIR / "config" / "mission_profiles" / "rover_mobility_and_terrain_navigation_v1.json"
)


@dataclass(frozen=True)
class CandidateEvidenceContext:
    discovery_report: DiscoveryReport
    discovery_report_path: Path
    discovery_report_sha256: str
    candidate: CandidateResult
    scale_bridge: dict[str, Any]
    scale_bridge_report_path: Path
    scale_bridge_report_sha256: str
    manifests: dict[str, DatasetManifest]
    manifest_paths: dict[str, Path]
    manifest_sha256: dict[str, str]
    profile: MissionAssessmentProfile
    profile_sha256: str
    terrain_twin: TerrainTwinMetadata | None
    terrain_twin_metadata_path: Path | None
    terrain_twin_metadata_sha256: str | None
    terrain_mesh_sha256: str | None

    @property
    def source_processing_sha256(self) -> dict[str, str]:
        return _source_processing_sha256(self.discovery_report)


def load_mission_profile(profile_id: str) -> tuple[MissionAssessmentProfile, str]:
    try:
        profile = MissionAssessmentProfile.model_validate_json(MISSION_PROFILE_PATH.read_text())
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=503, detail="Configured mission profile is invalid"
        ) from exc
    if profile.profile_id != profile_id:
        raise HTTPException(status_code=422, detail=f"Unsupported mission profile: {profile_id}")
    return profile, sha256_file(MISSION_PROFILE_PATH)


def _manifest_path(dataset_id: str) -> Path:
    if not _DATASET_ID.fullmatch(dataset_id):
        raise HTTPException(status_code=503, detail="Discovery report has an invalid dataset ID")
    matches = list(settings.manifests_dir.rglob(f"{dataset_id}.json"))
    if len(matches) != 1:
        raise HTTPException(
            status_code=503, detail="Source dataset manifest is missing or ambiguous"
        )
    return matches[0]


def _verified_raw_raster(manifest: DatasetManifest) -> Path:
    root = (settings.raw_data_dir / manifest.target_body).resolve()
    candidates = [
        path.resolve()
        for suffix in (".img", ".IMG", ".tif", ".tiff", ".jp2", ".hgt")
        for path in root.glob(f"{manifest.id}{suffix}")
    ]
    candidates = [path for path in candidates if path.is_relative_to(root) and path.is_file()]
    if len(candidates) != 1:
        raise HTTPException(
            status_code=503, detail="Immutable source raster is missing or ambiguous"
        )
    if sha256_file(candidates[0]) != manifest.checksum_sha256:
        raise HTTPException(status_code=503, detail="Source raster checksum differs from manifest")
    return candidates[0]


def _matching_twin(
    candidate: CandidateResult,
    report: DiscoveryReport,
    earth_manifest: DatasetManifest,
) -> tuple[TerrainTwinMetadata | None, Path | None, str | None, str | None]:
    root = (settings.derived_data_dir / "terrain_twins").resolve()
    for path in sorted(
        root.glob("*/metadata.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True
    ):
        try:
            raw = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if (
            raw.get("candidate_id") != candidate.candidate_id
            or raw.get("discovery_run_id") != report.run_id
            or raw.get("source_dataset_id") != earth_manifest.id
        ):
            continue
        twin_id = raw.get("terrain_twin_id")
        if not isinstance(twin_id, str) or not _TWIN_ID.fullmatch(twin_id):
            raise HTTPException(status_code=503, detail="Terrain Twin identifier is invalid")
        twin_directory = path.parent.resolve()
        if not twin_directory.is_relative_to(root) or twin_directory.name != twin_id:
            raise HTTPException(status_code=503, detail="Terrain Twin provenance path is invalid")
        try:
            twin = TerrainTwinMetadata.model_validate(raw)
        except ValueError as exc:
            raise HTTPException(status_code=503, detail="Terrain Twin metadata is invalid") from exc
        mesh_path = twin_directory / "terrain.glb"
        if not mesh_path.is_file():
            raise HTTPException(status_code=503, detail="Terrain Twin mesh artifact is missing")
        return twin, path, sha256_file(path), sha256_file(mesh_path)
    return None, None, None, None


def load_candidate_evidence(candidate_id: str, profile_id: str) -> CandidateEvidenceContext:
    if not _CANDIDATE_ID.fullmatch(candidate_id):
        raise HTTPException(status_code=404, detail="Candidate was not found")
    profile, profile_sha256 = load_mission_profile(profile_id)
    report_path, raw_report = report_for_candidate(candidate_id)
    try:
        report = DiscoveryReport.model_validate(raw_report)
    except ValueError as exc:
        raise HTTPException(
            status_code=503, detail="Candidate discovery report is invalid"
        ) from exc
    candidate = next(
        (item for item in report.candidates if item.candidate_id == candidate_id), None
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate is not in the latest discovery run")
    if (
        report.mission_profile.profile_id != profile.profile_id
        or report.mission_profile.version != profile.version
        or set(report.mission_profile.required_features) != set(profile.required_features)
        or report.mission_profile.feature_weights != profile.weights
    ):
        raise HTTPException(
            status_code=422,
            detail="Candidate discovery profile differs from the configured assessment profile",
        )
    if not _DATASET_ID.fullmatch(report.planetary_dataset_id) or not _DATASET_ID.fullmatch(
        report.earth_dataset_id
    ):
        raise HTTPException(
            status_code=503, detail="Discovery report source dataset IDs are invalid"
        )

    manifest_paths: dict[str, Path] = {}
    manifests: dict[str, DatasetManifest] = {}
    manifest_sha256: dict[str, str] = {}
    for body, dataset_id in (
        ("planetary", report.planetary_dataset_id),
        ("earth", report.earth_dataset_id),
    ):
        path = _manifest_path(dataset_id)
        try:
            manifest = DatasetManifest.model_validate_json(path.read_text())
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=503, detail=f"{body.title()} dataset manifest is invalid"
            ) from exc
        expected_body = "mars" if body == "planetary" else "earth"
        if manifest.id != dataset_id or manifest.target_body != expected_body:
            raise HTTPException(
                status_code=503, detail=f"{body.title()} source manifest does not match report"
            )
        _verified_raw_raster(manifest)
        manifests[body] = manifest
        manifest_paths[body] = path
        manifest_sha256[body] = sha256_file(path)

    bridge_path = (
        settings.processed_data_dir / "scale_bridge" / report.scale_bridge_run_id / "report.json"
    )
    if not bridge_path.is_file():
        raise HTTPException(status_code=503, detail="Referenced ScaleBridge report is unavailable")
    try:
        bridge = json.loads(bridge_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=503, detail="Referenced ScaleBridge report is invalid"
        ) from exc
    if (
        bridge.get("run_id") != report.scale_bridge_run_id
        or bridge.get("planetary", {}).get("dataset_id") != report.planetary_dataset_id
        or bridge.get("earth", {}).get("dataset_id") != report.earth_dataset_id
    ):
        raise HTTPException(
            status_code=503, detail="ScaleBridge provenance does not match discovery run"
        )

    twin, twin_path, twin_sha256, mesh_sha256 = _matching_twin(
        candidate, report, manifests["earth"]
    )
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
        manifest_sha256=manifest_sha256,
        profile=profile,
        profile_sha256=profile_sha256,
        terrain_twin=twin,
        terrain_twin_metadata_path=twin_path,
        terrain_twin_metadata_sha256=twin_sha256,
        terrain_mesh_sha256=mesh_sha256,
    )


def _source_processing_sha256(report: DiscoveryReport) -> dict[str, str]:
    return {
        "planetary": report.planetary_source_sha256,
        "earth": report.earth_source_sha256,
    }


def build_candidate_assessment(context: CandidateEvidenceContext) -> MissionAssessment:
    return assess_candidate(
        context.candidate,
        context.discovery_report,
        context.profile,
        profile_sha256=context.profile_sha256,
        discovery_report_sha256=context.discovery_report_sha256,
        terrain_twin=context.terrain_twin,
    )


def get_candidate_assessment(candidate_id: str, profile_id: str) -> MissionAssessment:
    context = load_candidate_evidence(candidate_id, profile_id)
    return build_candidate_assessment(context)
