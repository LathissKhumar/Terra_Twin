"""Database-backed bounded runner for reproducible ScaleBridge-to-discovery jobs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.models.discovery_job import DiscoveryJob
from app.domain.schemas.analogue_discovery import DiscoveryConfig
from app.domain.schemas.datasets import DatasetManifest
from app.domain.schemas.discovery_jobs import DiscoveryJobRequest, DiscoveryJobStatus
from app.domain.schemas.observation_counts import ObservationCountsManifest
from app.domain.schemas.terrain_analytics import TerrainAnalyticsConfig
from app.engines.analogue_discovery import load_mission_profile, run_discovery
from app.engines.data_ingestion.ingestion import sha256_file
from app.engines.scale_bridge.engine import ObservationCountSource, run_scale_bridge
from app.engines.terrain_analytics.engine import analyze_terrain_raster

logger = get_logger("terratwin.discovery_jobs")
_DATASET_ID = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[0-9a-f]{20}$")
_ALLOWED_RASTER_SUFFIXES = (".img", ".tif", ".tiff", ".jp2", ".hgt")
_PIPELINE_VERSION = "terratwin-scientific-pipeline-2"
_runner_lock = threading.RLock()
_executor: ThreadPoolExecutor | None = None
_futures: dict[str, Future[None]] = {}

_sync_engine = create_engine(
    settings.sync_database_url,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=2,
    pool_timeout=settings.DATABASE_TIMEOUT_SECONDS,
    connect_args={"connect_timeout": settings.DATABASE_TIMEOUT_SECONDS},
)
_Session = sessionmaker(_sync_engine, expire_on_commit=False)


def _fingerprint(request: DiscoveryJobRequest) -> str:
    encoded = json.dumps(
        {
            "pipeline_version": _PIPELINE_VERSION,
            "request": request.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def _status(record: DiscoveryJob, *, reused: bool = False) -> DiscoveryJobStatus:
    return DiscoveryJobStatus(
        job_id=str(record.id),
        request_fingerprint=record.request_fingerprint,
        status=record.status,  # type: ignore[arg-type]
        stage=record.stage,
        progress_percent=record.progress_percent,
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        result_run_id=record.result_run_id,
        failure_code=record.failure_code,
        failure_message=record.failure_message,
        reused_existing_job=reused,
    )


def _raw_raster(manifest: DatasetManifest) -> Path:
    if not _DATASET_ID.fullmatch(manifest.id):
        raise ValueError("Dataset manifest has an invalid identifier")
    root = (settings.raw_data_dir / manifest.target_body).resolve()
    matches = [
        path.resolve()
        for suffix in _ALLOWED_RASTER_SUFFIXES
        for path in root.glob(f"{manifest.id}{suffix}")
    ]
    matches = [path for path in matches if path.is_relative_to(root) and path.is_file()]
    if len(matches) != 1:
        raise FileNotFoundError(f"Validated source raster for {manifest.id} is unavailable")
    if sha256_file(matches[0]) != manifest.checksum_sha256:
        raise ValueError(f"Source raster checksum differs from manifest {manifest.id}")
    return matches[0]


def _load_manifest(dataset_id: str) -> tuple[DatasetManifest, Path]:
    if not _DATASET_ID.fullmatch(dataset_id):
        raise ValueError("Dataset identifier is malformed")
    paths = list(settings.manifests_dir.glob(f"{dataset_id}.json"))
    if len(paths) != 1:
        raise FileNotFoundError(f"Dataset manifest {dataset_id} is missing or ambiguous")
    manifest = DatasetManifest.model_validate_json(paths[0].read_text())
    if manifest.id != dataset_id:
        raise ValueError("Dataset manifest identifier does not match its filename")
    return manifest, _raw_raster(manifest)


def _product_open_path(manifest: DatasetManifest) -> Path | None:
    """Resolve and checksum an explicitly manifested detached product label."""
    label_name = manifest.product_metadata.get("tile_label")
    if label_name is None:
        return None
    if not isinstance(label_name, str) or Path(label_name).name != label_name:
        raise ValueError("Dataset detached label metadata is invalid")
    root = (settings.raw_data_dir / manifest.target_body).resolve()
    label_path = (root / label_name).resolve()
    if not label_path.is_relative_to(root) or not label_path.is_file():
        raise FileNotFoundError("Validated source product label is unavailable")
    expected_checksum = manifest.product_metadata.get("tile_label_sha256")
    if isinstance(expected_checksum, str) and sha256_file(label_path) != expected_checksum:
        raise ValueError("Detached product label checksum differs from its manifest")
    return label_path


def _optional_mola_counts(topography: DatasetManifest) -> ObservationCountSource | None:
    if (
        topography.target_body != "mars"
        or topography.product_metadata.get("product_id") != "MEGT44N000HB"
    ):
        return None
    ancillary = settings.manifests_dir / "ancillary"
    for path in ancillary.glob("*.json"):
        try:
            manifest = ObservationCountsManifest.model_validate_json(path.read_text())
        except (OSError, ValueError):
            continue
        if manifest.source_topography_id != topography.id:
            continue
        raster = (settings.raw_data_dir / "mars" / f"{manifest.id}.img").resolve()
        root = (settings.raw_data_dir / "mars").resolve()
        if not raster.is_relative_to(root) or not raster.is_file():
            raise FileNotFoundError("MOLA observation-count raster is missing")
        if sha256_file(raster) != manifest.checksum_sha256:
            raise ValueError("MOLA observation-count checksum differs from its manifest")
        label = settings.raw_data_dir / "mars" / "MEGC44N000HB.lbl"
        label_path = label if label.is_file() else None
        return ObservationCountSource(raster_path=raster, manifest=manifest, open_path=label_path)
    return None


def _update(job_id: UUID, **values: Any) -> None:
    with _Session.begin() as session:
        record = session.get(DiscoveryJob, job_id)
        if record is None:
            return
        for key, value in values.items():
            setattr(record, key, value)
        record.updated_at = datetime.now(UTC)


def _publish(source_directory: Path, destination: Path) -> None:
    if not source_directory.is_dir():
        raise FileNotFoundError("A completed processing artifact directory is missing")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(source_directory)
        return
    os.replace(source_directory, destination)


def _run_pipeline(job_id: UUID, request: DiscoveryJobRequest) -> None:
    stage = "input_validation"
    staging_root = (settings.processed_data_dir / "jobs" / str(job_id) / "staging").resolve()
    try:
        _update(
            job_id,
            status="running",
            stage=stage,
            progress_percent=2,
            started_at=datetime.now(UTC),
        )
        planetary, planetary_path = _load_manifest(request.planetary_dataset_id)
        earth, earth_path = _load_manifest(request.earth_dataset_id)
        planetary_open_path = _product_open_path(planetary)
        if planetary.target_body not in {"mars", "moon"} or earth.target_body != "earth":
            raise ValueError("Discovery requires a Mars/Moon reference and an Earth candidate DEM")
        counts = _optional_mola_counts(planetary)
        stage = "scale_bridge"
        _update(job_id, stage=stage, progress_percent=8)
        scale_result = run_scale_bridge(
            planetary_raster=planetary_path,
            planetary_open_path=planetary_open_path,
            planetary_manifest=planetary,
            planetary_center=request.planetary_center,
            earth_raster=earth_path,
            earth_manifest=earth,
            earth_center=request.earth_center,
            support_width_m=request.support_width_m,
            support_height_m=request.support_height_m,
            planetary_support_width_m=request.planetary_reference_width_m,
            planetary_support_height_m=request.planetary_reference_height_m,
            target_resolution_m=request.target_resolution_m,
            minimum_valid_fraction_per_cell=request.minimum_valid_fraction_per_cell,
            output_dir=staging_root / "scale_bridge",
            planetary_observation_counts=counts,
        )
        stage = "terrain_analytics"
        _update(job_id, stage=stage, progress_percent=42)
        analytics_config = TerrainAnalyticsConfig(
            neighborhood_radius_m=scale_result.report.target_resolution_m
        )
        planetary_analytics = analyze_terrain_raster(
            scale_result.artifact_paths["planetary"],
            staging_root / "terrain_analytics" / "mars",
            analytics_config,
        )
        shared_landform_scale = planetary_analytics.report.features[
            "landform_morphology"
        ].normalization_scale_m
        earth_analytics = analyze_terrain_raster(
            scale_result.artifact_paths["earth"],
            staging_root / "terrain_analytics" / "earth",
            analytics_config.model_copy(
                update={
                    "landform_standardization_scale_m": shared_landform_scale,
                    "landform_morphology_enabled": shared_landform_scale is not None,
                }
            ),
        )
        stage = "analogue_discovery"
        _update(job_id, stage=stage, progress_percent=72)
        profile_path = (
            Path(__file__).resolve().parents[2]
            / "config"
            / "mission_profiles"
            / "rover_mobility_and_terrain_navigation.v1.json"
        )
        mission_profile = load_mission_profile(profile_path)
        discovery_config = DiscoveryConfig(
            candidate_width_m=request.candidate_width_m,
            candidate_height_m=request.candidate_height_m,
            candidate_stride_m=request.candidate_stride_m,
            minimum_evidence_coverage=request.minimum_evidence_coverage,
            minimum_feature_samples=request.minimum_feature_samples,
            maximum_candidate_count=request.maximum_candidate_count,
            bootstrap_replicates=request.bootstrap_replicates,
        )
        discovery = run_discovery(
            planetary_feature_dir=Path(planetary_analytics.feature_paths["slope"]).parent,
            planetary_analytics_report=Path(planetary_analytics.feature_paths["report"]),
            earth_feature_dir=Path(earth_analytics.feature_paths["slope"]).parent,
            earth_analytics_report=Path(earth_analytics.feature_paths["report"]),
            planetary_relative_dem=scale_result.artifact_paths["planetary"],
            earth_relative_dem=scale_result.artifact_paths["earth"],
            scale_bridge_report_path=scale_result.artifact_paths["report"],
            output_dir=staging_root / "analogue_discovery",
            config=discovery_config,
            mission_profile=mission_profile,
            progress_callback=lambda completed, total: _update(
                job_id,
                progress_percent=72 + int(24 * completed / total),
                stage=f"analogue_discovery:{completed}/{total}"[:40],
            ),
        )

        # Engine run directories are moved to their canonical stores only after
        # all processing succeeds. The discovery report publishes last, so no
        # candidate endpoint can expose partial jobs as completed results.
        stage_scale = staging_root / "scale_bridge" / scale_result.report.run_id
        stage_mars = staging_root / "terrain_analytics" / "mars" / planetary_analytics.report.run_id
        stage_earth = staging_root / "terrain_analytics" / "earth" / earth_analytics.report.run_id
        stage_discovery = staging_root / "analogue_discovery" / discovery.run_id
        _publish(
            stage_scale,
            settings.processed_data_dir / "scale_bridge" / scale_result.report.run_id,
        )
        _publish(
            stage_mars,
            settings.derived_data_dir
            / "terrain_analytics"
            / "mars"
            / planetary_analytics.report.run_id,
        )
        _publish(
            stage_earth,
            settings.derived_data_dir
            / "terrain_analytics"
            / "earth"
            / earth_analytics.report.run_id,
        )
        _publish(
            stage_discovery,
            settings.results_dir / "analogue_discovery" / discovery.run_id,
        )
        _update(
            job_id,
            status="succeeded",
            stage="completed",
            progress_percent=100,
            result_run_id=discovery.run_id,
            finished_at=datetime.now(UTC),
            failure_code=None,
            failure_message=None,
        )
        logger.info(
            "Discovery job completed",
            job_id=str(job_id),
            discovery_run_id=discovery.run_id,
            evaluated_candidates=discovery.evaluated_window_count,
            eligible_candidates=discovery.eligible_candidate_count,
        )
    except Exception as exc:
        safe_message = str(exc).replace(str(settings.DATA_DIR), "[configured-data]")[:500]
        failure_code = type(exc).__name__[:80]
        try:
            _update(
                job_id,
                status="failed",
                stage=f"failed:{stage}"[:40],
                failure_code=failure_code,
                failure_message=safe_message or "Processing failed without a diagnostic message",
                finished_at=datetime.now(UTC),
            )
        except Exception as update_exc:
            logger.error(
                "Could not persist discovery failure",
                job_id=str(job_id),
                exception_type=type(update_exc).__name__,
            )
        logger.error(
            "Discovery job failed",
            job_id=str(job_id),
            stage=stage,
            failure_code=failure_code,
        )
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)
        with _runner_lock:
            _futures.pop(str(job_id), None)


def _submit_existing(job_id: UUID, request_payload: dict[str, Any]) -> None:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="terratwin-discovery")
    request = DiscoveryJobRequest.model_validate(request_payload)
    _futures[str(job_id)] = _executor.submit(_run_pipeline, job_id, request)


def start_job_runner() -> None:
    """Recover durable queue state and mark process-interrupted jobs explicitly."""
    if settings.ENVIRONMENT == "test":
        return
    global _executor
    with _runner_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="terratwin-discovery")
        queued: list[tuple[UUID, dict[str, Any]]] = []
        with _Session.begin() as session:
            now = datetime.now(UTC)
            interrupted = session.scalars(
                select(DiscoveryJob).where(DiscoveryJob.status == "running")
            ).all()
            for record in interrupted:
                record.status = "interrupted"
                record.stage = "interrupted"
                record.failure_code = "WorkerInterrupted"
                record.failure_message = "Backend stopped while this job was processing."
                record.result_run_id = None
                record.finished_at = now
                record.updated_at = now
            queued_records = session.scalars(
                select(DiscoveryJob)
                .where(DiscoveryJob.status == "queued")
                .order_by(DiscoveryJob.created_at)
            ).all()
            queued = [(record.id, record.request_payload) for record in queued_records]
        for job_id, payload in queued:
            _submit_existing(job_id, payload)


def stop_job_runner() -> None:
    global _executor
    with _runner_lock:
        executor, _executor = _executor, None
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=False)


def submit_discovery_job(request: DiscoveryJobRequest) -> DiscoveryJobStatus:
    fingerprint = _fingerprint(request)
    with _runner_lock, _Session() as session:
        reusable = session.scalar(
            select(DiscoveryJob)
            .where(
                DiscoveryJob.request_fingerprint == fingerprint,
                DiscoveryJob.status.in_(["queued", "running", "succeeded"]),
            )
            .order_by(DiscoveryJob.created_at.desc())
        )
        if reusable is not None:
            return _status(reusable, reused=True)
        pending = session.scalar(
            select(func.count())
            .select_from(DiscoveryJob)
            .where(DiscoveryJob.status.in_(["queued", "running"]))
        )
        if int(pending or 0) >= 2:
            raise RuntimeError("Discovery processing capacity is full; retry after a job finishes")
        record = DiscoveryJob(
            request_fingerprint=fingerprint,
            request_payload=request.model_dump(mode="json"),
            status="queued",
            stage="queued",
            progress_percent=0,
        )
        session.add(record)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raced = session.scalar(
                select(DiscoveryJob).where(
                    DiscoveryJob.request_fingerprint == fingerprint,
                    DiscoveryJob.status.in_(["queued", "running"]),
                )
            )
            if raced is None:
                raise
            return _status(raced, reused=True)
        session.refresh(record)
        result = _status(record)
        _submit_existing(record.id, record.request_payload)
        return result


def get_discovery_job(job_id: UUID) -> DiscoveryJobStatus | None:
    with _Session() as session:
        record = session.get(DiscoveryJob, job_id)
        return _status(record) if record is not None else None


def list_discovery_jobs(limit: int, offset: int) -> tuple[list[DiscoveryJobStatus], int]:
    with _Session() as session:
        total = int(session.scalar(select(func.count()).select_from(DiscoveryJob)) or 0)
        records = session.scalars(
            select(DiscoveryJob)
            .order_by(DiscoveryJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return [_status(record) for record in records], total
