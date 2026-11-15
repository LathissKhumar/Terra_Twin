"""Scientific checks for DEM mesh generation and independent validation."""

from __future__ import annotations

import json
import math
import struct
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.domain.schemas.datasets import DatasetManifest
from app.domain.schemas.terrain_twin import TerrainTwinCandidate
from app.engines.data_ingestion.ingestion import sha256_file
from app.engines.terrain_twin.engine import (
    _calculate_normals,
    _reproject_valid_mask,
    _write_glb,
    _write_preview,
    create_terrain_twin,
)
from app.engines.validation.engine import (
    ValidationUnavailable,
    compare_independent_dem,
    summarize_elevation_errors,
)


def _manifest(
    path: Path, *, dataset_id: str | None = None, vertical_reference: str = "EGM2008"
) -> DatasetManifest:
    with rasterio.open(path) as raster:
        bounds = raster.bounds
        width, height = raster.width, raster.height
        resolution = raster.res
        crs = raster.crs
        dtype = raster.dtypes[0]
    checksum = sha256_file(path)
    return DatasetManifest(
        id=dataset_id or checksum,
        target_body="earth",
        provider="Documented test fixture provider",
        product="Small test-only elevation raster",
        version="test fixture",
        source_url=None,
        downloaded_at=datetime.now(UTC),
        checksum_sha256=checksum,
        file_size_bytes=path.stat().st_size,
        crs=crs.to_string(),
        bounds=(bounds.left, bounds.bottom, bounds.right, bounds.top),
        width=width,
        height=height,
        pixel_resolution_x=abs(resolution[0]),
        pixel_resolution_y=abs(resolution[1]),
        resolution_unit="degrees",
        vertical_units="m",
        vertical_reference=vertical_reference,
        nodata=-9999.0,
        dtype=dtype,
        processing_status="validated",
        license="test fixture",
        attribution="Synthetic test fixture; not a scientific dataset",
        media_type="GTiff",
    )


def _candidate(source_id: str) -> TerrainTwinCandidate:
    return TerrainTwinCandidate(
        candidate_id="a" * 24,
        discovery_run_id="test-run",
        discovery_status="insufficient_evidence",
        ranking=None,
        centroid_wgs84=(77.0018, 18.0006),
        geographic_boundary_wgs84=[
            (77.0013, 18.0001),
            (77.0023, 18.0001),
            (77.0023, 18.0011),
            (77.0013, 18.0011),
            (77.0013, 18.0001),
        ],
        source_dataset_id=source_id,
        source_product="Small test-only elevation raster",
    )


def _parse_glb(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    magic, version, total_length = struct.unpack_from("<III", payload, 0)
    assert magic == 0x46546C67
    assert version == 2
    assert total_length == len(payload)
    json_length, json_type = struct.unpack_from("<II", payload, 12)
    assert json_type == 0x4E4F534A
    document = json.loads(payload[20 : 20 + json_length].decode("utf-8"))
    binary_offset = 20 + json_length
    binary_length, binary_type = struct.unpack_from("<II", payload, binary_offset)
    assert binary_type == 0x004E4942
    binary = payload[binary_offset + 8 : binary_offset + 8 + binary_length]
    return document, binary


def test_mesh_chunking_skips_cells_that_overlap_nodata_holes(tmp_path: Path) -> None:
    elevation = np.arange(25, dtype="float32").reshape(5, 5)
    valid = np.ones((5, 5), dtype=bool)
    valid[2, 2] = False
    elevation[~valid] = np.nan
    normals = _calculate_normals(elevation, valid, 10, 10)
    mesh = tmp_path / "hole.glb"
    vertices, chunks = _write_glb(
        mesh,
        elevation,
        valid,
        normals,
        from_origin(500_000, 2_000_000, 10, 10),
        stride=1,
        chunk_cells=2,
        vertical_exaggeration=1,
        elevation_origin_m=12,
        metadata={"verticalUnits": "m", "verticalExaggeration": 1},
    )
    document, _ = _parse_glb(mesh)
    index_counts = [
        document["accessors"][primitive["indices"]]["count"]
        for item in document["meshes"]
        for primitive in item["primitives"]
    ]
    assert chunks == 4
    assert vertices == 36
    assert sum(index_counts) == 12 * 6
    assert all(item["primitives"][0]["mode"] == 4 for item in document["meshes"])


def test_dem_mesh_preserves_source_metadata_and_reports_validation_unavailable(
    tmp_path: Path,
) -> None:
    values = np.fromfunction(lambda row, col: 500 + row * 0.5 + col * 0.25, (12, 12)).astype(
        "float32"
    )
    values[5, 5] = -9999
    source = tmp_path / "source.tif"
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=12,
        height=12,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(77.0012, 18.0012, 0.0001, 0.0001),
        nodata=-9999,
    ) as raster:
        raster.write(values, 1)
    manifest = _manifest(source, vertical_reference="EGM2008 orthometric height")
    original_sha = sha256_file(source)
    result = create_terrain_twin(
        candidate=_candidate(manifest.id),
        source_path=source,
        source_manifest=manifest,
        output_directory=tmp_path / "twin",
        max_vertices=1_000,
        chunk_cells=32,
        vertical_exaggeration=1,
        artifact_base_url="/api/v1/terrain-twins/0123456789abcdef01234567",
    )
    twin_directory = tmp_path / "twin"
    document, binary = _parse_glb(twin_directory / "terrain.glb")
    extras = document["asset"]["extras"]
    vertical_ranges: list[float] = []
    triangle_index_count = 0
    for mesh in document["meshes"]:
        for primitive in mesh["primitives"]:
            position_accessor = document["accessors"][primitive["attributes"]["POSITION"]]
            position_view = document["bufferViews"][position_accessor["bufferView"]]
            position_offset = position_view.get("byteOffset", 0) + position_accessor.get(
                "byteOffset", 0
            )
            positions = np.frombuffer(
                binary,
                dtype="<f4",
                count=position_accessor["count"] * 3,
                offset=position_offset,
            ).reshape(-1, 3)
            vertical_ranges.append(float(np.ptp(positions[:, 1])))
            triangle_index_count += document["accessors"][primitive["indices"]]["count"]
    assert result.validation_status == "unvalidated"
    assert result.validation_metrics is None
    assert result.source_vertical_units == "m"
    assert result.source_vertical_reference == "EGM2008 orthometric height"
    assert result.vertical_exaggeration == 1
    assert result.source_nodata_cell_count > 0
    assert result.source_candidate_exterior_cell_count > 0
    assert result.actual_vertex_count <= result.max_vertices
    assert result.chunk_count >= 1
    assert extras["sourceSha256"] == original_sha
    assert extras["verticalExaggeration"] == 1
    assert extras["coordinateAxisOrder"] == "east, up, north"
    assert max(vertical_ranges) > 0
    assert triangle_index_count > 0
    assert extras["geographicBoundsWgs84"] == list(result.geographic_bounds_wgs84)
    assert (twin_directory / "elevation.png").read_bytes().startswith(b"\x89PNG")
    assert (twin_directory / "slope.png").read_bytes().startswith(b"\x89PNG")
    assert (twin_directory / "error_map_unavailable.svg").is_file()
    assert (twin_directory / "valid_comparison_mask_unavailable.svg").is_file()
    assert sha256_file(source) == original_sha


def test_error_statistics_match_manual_values_and_common_mask() -> None:
    source = np.array([[11.0, 10.0], [10.0, 8.0]])
    reference = np.array([[10.0, 10.0], [9.0, 10.0]])
    valid = np.array([[True, True], [True, False]])
    metrics = summarize_elevation_errors(
        source, reference, valid, pixel_area_m2=100, resampling="none"
    )
    assert metrics.mean_absolute_error_m == pytest.approx(2 / 3)
    assert metrics.root_mean_square_error_m == pytest.approx(math.sqrt(2 / 3))
    assert metrics.median_absolute_error_m == pytest.approx(1)
    assert metrics.mean_bias_m == pytest.approx(2 / 3)
    assert metrics.valid_sample_count == 3
    assert metrics.valid_comparison_area_m2 == pytest.approx(300)
    assert metrics.valid_coverage == pytest.approx(0.75)


def test_independent_dem_comparison_rejects_same_source_and_vertical_mismatch(
    tmp_path: Path,
) -> None:
    transform = from_origin(500_000, 2_000_000, 30, 30)
    source = tmp_path / "source.tif"
    reference = tmp_path / "reference.tif"
    for path, elevation in ((source, 100), (reference, 102)):
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=4,
            height=4,
            count=1,
            dtype="int16",
            crs="EPSG:32643",
            transform=transform,
            nodata=-9999,
        ) as raster:
            raster.write(np.full((4, 4), elevation, dtype="int16"), 1)
            if path == source:
                raster.update_tags(
                    dataset_id="a" * 64,
                    source_sha256="b" * 64,
                    surface_semantics="piecewise-planar surface of exported mesh",
                )
    args = {
        "source_path": source,
        "reference_path": reference,
        "source_sha256": "b" * 64,
        "reference_sha256": sha256_file(reference),
        "source_dataset_id": "a" * 64,
        "reference_dataset_id": "c" * 64,
        "source_provider": "mesh source provider",
        "reference_provider": "independent survey provider",
        "source_product": "mesh source product",
        "reference_product": "independent survey product",
        "source_vertical_reference": "EGM2008",
        "reference_vertical_reference": "EGM2008",
        "source_vertical_units": "m",
        "reference_vertical_units": "m",
    }
    source_values, reference_values, mask, metrics = compare_independent_dem(**args)
    assert mask.all()
    assert metrics.mean_absolute_error_m == pytest.approx(2)
    assert metrics.mean_bias_m == pytest.approx(-2)
    assert np.all(source_values - reference_values == -2)
    with pytest.raises(ValidationUnavailable, match="Vertical references differ"):
        compare_independent_dem(**{**args, "reference_vertical_reference": "EGM96"})
    with pytest.raises(ValidationUnavailable, match="identical"):
        compare_independent_dem(**{**args, "reference_dataset_id": "a" * 64})


def test_validation_rejects_same_raster_even_if_caller_claims_different_hashes(
    tmp_path: Path,
) -> None:
    raster_path = tmp_path / "mesh_surface.tif"
    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        width=4,
        height=4,
        count=1,
        dtype="float32",
        crs="EPSG:32643",
        transform=from_origin(500_000, 2_000_000, 30, 30),
        nodata=-9999,
    ) as raster:
        raster.write(np.ones((4, 4), dtype="float32"), 1)
        raster.update_tags(
            dataset_id="a" * 64,
            source_sha256="b" * 64,
            surface_semantics="piecewise-planar surface of exported mesh",
        )
    args = {
        "source_path": raster_path,
        "reference_path": raster_path,
        "source_sha256": "b" * 64,
        "reference_sha256": "c" * 64,
        "source_dataset_id": "a" * 64,
        "reference_dataset_id": "d" * 64,
        "source_provider": "A",
        "reference_provider": "B",
        "source_product": "A product",
        "reference_product": "B product",
        "source_vertical_reference": "EGM2008",
        "reference_vertical_reference": "EGM2008",
        "source_vertical_units": "m",
        "reference_vertical_units": "m",
    }
    with pytest.raises(ValidationUnavailable, match="same raster"):
        compare_independent_dem(**args)


def test_validation_aggregates_to_coarsest_nominal_support_not_fine_source_pixels(
    tmp_path: Path,
) -> None:
    transform = from_origin(500_000, 2_000_000, 10, 10)
    source = tmp_path / "mesh.tif"
    reference = tmp_path / "reference.tif"
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=12,
        height=12,
        count=1,
        dtype="float32",
        crs="EPSG:32643",
        transform=transform,
        nodata=-9999,
    ) as raster:
        raster.write(np.full((12, 12), 100, dtype="float32"), 1)
        raster.update_tags(
            dataset_id="a" * 64,
            source_sha256="b" * 64,
            surface_semantics="piecewise-planar surface of exported mesh",
        )
    with rasterio.open(
        reference,
        "w",
        driver="GTiff",
        width=4,
        height=4,
        count=1,
        dtype="float32",
        crs="EPSG:32643",
        transform=from_origin(500_000, 2_000_000, 30, 30),
        nodata=-9999,
    ) as raster:
        raster.write(np.full((4, 4), 102, dtype="float32"), 1)
    _, _, mask, metrics = compare_independent_dem(
        source,
        reference,
        source_sha256="b" * 64,
        reference_sha256=sha256_file(reference),
        source_dataset_id="a" * 64,
        reference_dataset_id="c" * 64,
        source_provider="source provider",
        reference_provider="reference provider",
        source_product="source product",
        reference_product="reference product",
        source_vertical_reference="EGM2008",
        reference_vertical_reference="EGM2008",
        source_vertical_units="m",
        reference_vertical_units="m",
    )
    assert metrics.comparison_support_m == pytest.approx(30)
    assert metrics.valid_sample_count <= 16
    assert mask.shape == (4, 4)


def test_nodata_in_slope_preview_is_handled_without_becoming_zero(tmp_path: Path) -> None:
    elevation = np.arange(25, dtype="float32").reshape(5, 5)
    valid = np.ones((5, 5), dtype=bool)
    valid[2, 2] = False
    elevation[~valid] = np.nan
    output = tmp_path / "slope.png"
    _write_preview(output, elevation, valid, "slope", (30, 30))
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_mask_reprojection_preserves_zero_as_invalid() -> None:
    valid = np.ones((4, 4), dtype=bool)
    valid[1, 2] = False
    transform = from_origin(500_000, 2_000_000, 30, 30)
    projected = _reproject_valid_mask(
        valid,
        source_transform=transform,
        source_crs=rasterio.crs.CRS.from_epsg(32643),
        destination_transform=transform,
        destination_crs=rasterio.crs.CRS.from_epsg(32643),
        destination_shape=valid.shape,
    )
    assert np.array_equal(projected, valid)
