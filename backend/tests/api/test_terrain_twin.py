"""Route checks using the documented compact real Copernicus test window."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import rasterio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.domain.schemas.datasets import DatasetManifest
from app.engines.data_ingestion.ingestion import sha256_file
from app.main import app

FIXTURE = Path(__file__).parents[1] / "fixtures" / "data" / "copernicus_glo30_n18_e077_window.tif"
DATASET_ID = "51587b0a9af347ff0bfe95b51ccd4d145ffdf0f74fdf18ce0213028f8041d989"
CANDIDATE_ID = "a" * 24


@pytest.fixture
def terrain_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    root = tmp_path / "data"
    raw = root / "raw" / "earth"
    raw.mkdir(parents=True)
    source = raw / f"{DATASET_ID}.tif"
    shutil.copyfile(FIXTURE, source)
    with rasterio.open(source) as raster:
        west, south, east, north = raster.bounds
        width, height = raster.width, raster.height
        res_x, res_y = raster.res
        crs = raster.crs.to_string()
        dtype = raster.dtypes[0]
        nodata = raster.nodata
    manifest = DatasetManifest(
        id=DATASET_ID,
        target_body="earth",
        provider="Copernicus Programme; public AWS mirror",
        product="Copernicus DEM GLO-30 Public DSM test window",
        version="2021 release",
        source_url="https://copernicus-dem-30m.s3.amazonaws.com/",
        downloaded_at=datetime(2026, 11, 15, tzinfo=UTC),
        checksum_sha256=sha256_file(source),
        file_size_bytes=source.stat().st_size,
        crs=crs,
        bounds=(west, south, east, north),
        width=width,
        height=height,
        pixel_resolution_x=abs(res_x),
        pixel_resolution_y=abs(res_y),
        resolution_unit="degrees",
        vertical_units="m",
        vertical_reference="EGM2008 orthometric height",
        nodata=nodata,
        dtype=dtype,
        processing_status="validated",
        license="Copernicus DEM License",
        attribution="Copernicus Programme",
        media_type="image/tiff",
    )
    manifests = root / "manifests" / DATASET_ID
    manifests.mkdir(parents=True)
    (manifests / f"{DATASET_ID}.json").write_text(manifest.model_dump_json())
    report_dir = root / "results" / "analogue_discovery" / "fixture-run"
    report_dir.mkdir(parents=True)
    margin_x = (east - west) * 0.02
    margin_y = (north - south) * 0.02
    west_inner, east_inner = west + margin_x, east - margin_x
    south_inner, north_inner = south + margin_y, north - margin_y
    boundary = [
        [west_inner, south_inner],
        [east_inner, south_inner],
        [east_inner, north_inner],
        [west_inner, north_inner],
        [west_inner, south_inner],
    ]
    (report_dir / "report.json").write_text(
        json.dumps(
            {
                "run_id": "fixture-run",
                "earth_source_product": manifest.product,
                "candidates": [
                    {
                        "candidate_id": CANDIDATE_ID,
                        "status": "insufficient_evidence",
                        "ranking": None,
                        "centroid_wgs84": [
                            (west_inner + east_inner) / 2,
                            (south_inner + north_inner) / 2,
                        ],
                        "geographic_boundary_wgs84": boundary,
                        "source_dataset_ids": {"earth": DATASET_ID},
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(settings, "DATA_DIR", root)
    return root, sha256_file(source)


@pytest.mark.asyncio
async def test_candidate_mesh_api_returns_provenance_and_allowlisted_artifacts(
    terrain_data_root: tuple[Path, str],
) -> None:
    root, original_checksum = terrain_data_root
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        candidates = await client.get("/api/v1/terrain-twins/candidates")
        assert candidates.status_code == 503
        assert "verified bare-earth Earth DEM" in candidates.json()["error"]["message"]
        created = await client.post(f"/api/v1/terrain-twins/candidates/{CANDIDATE_ID}", json={})
        assert created.status_code == 201, created.text
        metadata = created.json()
        assert metadata["validation_status"] == "unvalidated"
        assert metadata["source_candidate_exterior_cell_count"] >= 0
        assert metadata["source_nodata_cell_count"] >= 0
        assert metadata["source_sha256"] == original_checksum
        assert metadata["discovery_status"] == "insufficient_evidence"
        twin_id = metadata["terrain_twin_id"]
        existing = await client.get(f"/api/v1/terrain-twins/candidates/{CANDIDATE_ID}/existing")
        assert existing.status_code == 200
        assert existing.json()["terrain_twin_id"] == twin_id
        fetched = await client.get(f"/api/v1/terrain-twins/{twin_id}")
        assert fetched.status_code == 200
        assert fetched.json()["terrain_twin_id"] == twin_id
        mesh = await client.get(f"/api/v1/terrain-twins/{twin_id}/artifacts/mesh")
        assert mesh.status_code == 200
        assert mesh.headers["content-type"].startswith("model/gltf-binary")
        assert mesh.content[:4] == b"glTF"
        assert sha256_file(root / "raw" / "earth" / f"{DATASET_ID}.tif") == original_checksum


@pytest.mark.asyncio
async def test_terrain_twin_api_rejects_invalid_candidate_and_unbounded_options() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.post(f"/api/v1/terrain-twins/candidates/{'x' * 24}", json={})
        bad_options = await client.post(
            f"/api/v1/terrain-twins/candidates/{CANDIDATE_ID}",
            json={"max_vertices": 999_999},
        )
    assert missing.status_code == 404
    assert bad_options.status_code == 422
