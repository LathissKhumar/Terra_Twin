"""Durable job submission, status and actual candidate retrieval."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.domain.schemas.analogue_discovery import DiscoveryReport
from app.domain.schemas.discovery_jobs import (
    DiscoveryJobPage,
    DiscoveryJobRequest,
    DiscoveryJobStatus,
)
from app.services.discovery_jobs import (
    get_discovery_job,
    list_discovery_jobs,
    submit_discovery_job,
)

router = APIRouter(prefix="/discovery", tags=["Discovery"])


def _job_uuid(job_id: str) -> UUID:
    try:
        return UUID(job_id)
    except ValueError as exc:
        raise HTTPException(404, "Discovery job was not found") from exc


def _report_for_job(job: DiscoveryJobStatus) -> DiscoveryReport:
    if job.status != "succeeded" or job.result_run_id is None:
        raise HTTPException(409, "Discovery job has no completed candidate results")
    run_id = job.result_run_id
    if len(run_id) != 20 or any(char not in "0123456789abcdef" for char in run_id):
        raise HTTPException(503, "Stored discovery result identifier is invalid")
    report_path = settings.results_dir / "analogue_discovery" / run_id / "report.json"
    try:
        return DiscoveryReport.model_validate_json(report_path.read_text())
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Completed discovery report is unavailable or invalid") from exc


@router.post("/jobs", response_model=DiscoveryJobStatus, status_code=status.HTTP_202_ACCEPTED)
def create_discovery_job(request: DiscoveryJobRequest, response: Response) -> DiscoveryJobStatus:
    try:
        result = submit_discovery_job(request)
    except RuntimeError as exc:
        raise HTTPException(429, str(exc), headers={"Retry-After": "10"}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Discovery job storage is unavailable") from exc
    if result.reused_existing_job:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("/jobs", response_model=DiscoveryJobPage)
def get_discovery_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DiscoveryJobPage:
    try:
        items, total = list_discovery_jobs(limit, offset)
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Discovery job storage is unavailable") from exc
    return DiscoveryJobPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/jobs/{job_id}", response_model=DiscoveryJobStatus)
def get_discovery_job_status(job_id: str) -> DiscoveryJobStatus:
    try:
        result = get_discovery_job(_job_uuid(job_id))
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Discovery job storage is unavailable") from exc
    if result is None:
        raise HTTPException(404, "Discovery job was not found")
    return result


@router.get("/jobs/{job_id}/candidates")
def get_discovery_candidates(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    minimum_coverage: float = Query(default=0, ge=0, le=1),
) -> dict[str, object]:
    try:
        job = get_discovery_job(_job_uuid(job_id))
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Discovery job storage is unavailable") from exc
    if job is None:
        raise HTTPException(404, "Discovery job was not found")
    report = _report_for_job(job)
    filtered = [item for item in report.candidates if item.evidence_coverage >= minimum_coverage]
    filtered.sort(
        key=lambda item: (
            item.ranking is None,
            item.ranking if item.ranking is not None else float("inf"),
            -item.evidence_coverage,
            item.candidate_id,
        )
    )
    return {
        "job": job.model_dump(mode="json"),
        "discovery_run_id": report.run_id,
        "searched_boundary_wgs84": report.search_boundary_wgs84,
        "generated_window_count": report.generated_window_count,
        "evaluated_window_count": report.evaluated_window_count,
        "eligible_candidate_count": report.eligible_candidate_count,
        "ranked_candidate_count": report.ranked_candidate_count,
        "minimum_coverage_filter": minimum_coverage,
        "items": [item.model_dump(mode="json") for item in filtered[offset : offset + limit]],
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
        "warnings": report.warnings,
    }


@router.get("/jobs/{job_id}/report", response_model=DiscoveryReport)
def get_discovery_report(job_id: str) -> DiscoveryReport:
    try:
        job = get_discovery_job(_job_uuid(job_id))
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Discovery job storage is unavailable") from exc
    if job is None:
        raise HTTPException(404, "Discovery job was not found")
    return _report_for_job(job)
