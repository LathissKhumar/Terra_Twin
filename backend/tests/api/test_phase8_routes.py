from fastapi.testclient import TestClient

from app.main import app


def test_phase8_routes_are_mounted_and_validation_is_structured() -> None:
    with TestClient(app) as client:
        mission = client.get("/api/v1/missions")
        assert mission.status_code == 200
        assert "reference_regions" in mission.json()

        invalid_job = client.post("/api/v1/discovery/jobs", json={})
        assert invalid_job.status_code == 422
        assert invalid_job.json()["error"]["type"] == "RequestValidationError"

        invalid_candidate = client.get("/api/v1/terrain/candidates/../../etc/passwd")
        assert invalid_candidate.status_code in {404, 422}


def test_malformed_feature_preview_run_id_is_not_opened() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/terrain/discovery-runs/../../features/earth/slope/preview/not-a-candidate"
        )
    assert response.status_code in {404, 422}
