import os
from uuid import UUID

import pytest

from app.domain.models.discovery_job import DiscoveryJob
from app.domain.schemas.discovery_jobs import DiscoveryJobRequest
from app.domain.schemas.scale_bridge import GeographicCenter
from app.services import discovery_jobs


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1 for live database"
)
def test_discovery_job_is_durable_and_duplicate_submission_is_reused(monkeypatch) -> None:
    request = DiscoveryJobRequest(
        planetary_dataset_id="a" * 64,
        earth_dataset_id="b" * 64,
        planetary_center=GeographicCenter(longitude=77.5, latitude=18.4),
        earth_center=GeographicCenter(longitude=77.5, latitude=18.5),
    )
    monkeypatch.setattr(discovery_jobs, "_submit_existing", lambda *_args: None)
    first = discovery_jobs.submit_discovery_job(request)
    try:
        second = discovery_jobs.submit_discovery_job(request)
        assert first.status == "queued"
        assert second.job_id == first.job_id
        assert second.reused_existing_job is True
        stored = discovery_jobs.get_discovery_job(UUID(first.job_id))
        assert stored is not None
        assert stored.request_fingerprint == first.request_fingerprint
        assert stored.request_fingerprint == discovery_jobs._fingerprint(request)
    finally:
        with discovery_jobs._Session.begin() as session:
            session.delete(session.get(DiscoveryJob, UUID(first.job_id)))


def test_fingerprint_changes_when_scientific_pipeline_version_changes(monkeypatch) -> None:
    request = DiscoveryJobRequest(
        planetary_dataset_id="a" * 64,
        earth_dataset_id="b" * 64,
        planetary_center={"longitude": 77.52, "latitude": 18.46},
        earth_center={"longitude": 77.5, "latitude": 18.5},
        planetary_reference_width_m=2_000,
        planetary_reference_height_m=2_000,
        candidate_width_m=2_000,
        candidate_height_m=2_000,
    )
    first = discovery_jobs._fingerprint(request)
    monkeypatch.setattr(discovery_jobs, "_PIPELINE_VERSION", "next-scientific-pipeline")
    assert discovery_jobs._fingerprint(request) != first
