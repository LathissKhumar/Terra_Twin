"""Numerical and provenance checks for ScaleBridge's public entry point."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pyproj import CRS, Transformer
from rasterio.transform import from_origin

from app.core.exceptions import (
    CoordinateTransformationError,
    IncompatibleVerticalUnitsError,
    InvalidRasterError,
)
from app.domain.schemas.datasets import DatasetManifest
from app.domain.schemas.observation_counts import ObservationCountsManifest
from app.engines.scale_bridge.engine import ObservationCountSource, run_scale_bridge

MARS_CRS = CRS.from_proj4(
    "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=180 +a=3396000 +b=3396000 +units=m +no_defs"
)


def make_dataset(
    path: Path,
    *,
    values: np.ndarray,
    crs: CRS,
    transform: rasterio.Affine,
    body: str,
    vertical_units: str = "m",
    vertical_reference: str = "local datum",
    nodata: float | None = -9999.0,
    effective_resolution_m: float | None = None,
    valid_mask: np.ndarray | None = None,
) -> DatasetManifest:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dataset:
        dataset.write(values.astype("float32"), 1)
        if valid_mask is not None:
            dataset.write_mask(valid_mask.astype("uint8") * 255)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with rasterio.open(path) as dataset:
        bounds = dataset.bounds
        resolution = dataset.res
        width, height = dataset.width, dataset.height
        driver = dataset.driver
    metadata: dict[str, str | int | float | None] = {}
    if effective_resolution_m is not None:
        metadata["effective_resolution_m"] = effective_resolution_m
    return DatasetManifest(
        id=digest,
        target_body=body,  # type: ignore[arg-type]
        provider="Numerical test fixture",
        product="Synthetic analytical surface for tests only",
        downloaded_at=datetime.now(UTC),
        checksum_sha256=digest,
        file_size_bytes=path.stat().st_size,
        crs=crs.to_wkt(),
        bounds=(bounds.left, bounds.bottom, bounds.right, bounds.top),
        width=width,
        height=height,
        pixel_resolution_x=abs(resolution[0]),
        pixel_resolution_y=abs(resolution[1]),
        resolution_unit="source CRS units",
        vertical_units=vertical_units,
        vertical_reference=vertical_reference,
        nodata=nodata,
        dtype="float32",
        processing_status="validated",
        attribution="Test-only analytical surface; not a measured elevation dataset",
        media_type=driver,
        product_metadata=metadata,
    )


def make_pair(
    tmp_path: Path,
    mars: np.ndarray,
    earth: np.ndarray,
    *,
    mars_cell: float = 100.0,
    earth_cell: float = 30.0,
    earth_nodata: float | None = -9999.0,
    earth_valid_mask: np.ndarray | None = None,
):
    lon, lat = 77.5, 18.4
    mars_transformer = Transformer.from_crs(MARS_CRS.geodetic_crs, MARS_CRS, always_xy=True)
    mars_x, mars_y = mars_transformer.transform(lon, lat)
    earth_crs = CRS.from_epsg(32643)
    earth_transformer = Transformer.from_crs("EPSG:4326", earth_crs, always_xy=True)
    earth_x, earth_y = earth_transformer.transform(lon, lat)
    mars_path, earth_path = tmp_path / "mars.tif", tmp_path / "earth.tif"
    mars_manifest = make_dataset(
        mars_path,
        values=mars,
        crs=MARS_CRS,
        transform=from_origin(
            mars_x - mars.shape[1] * mars_cell / 2,
            mars_y + mars.shape[0] * mars_cell / 2,
            mars_cell,
            mars_cell,
        ),
        body="mars",
    )
    earth_manifest = make_dataset(
        earth_path,
        values=earth,
        crs=earth_crs,
        transform=from_origin(
            earth_x - earth.shape[1] * earth_cell / 2,
            earth_y + earth.shape[0] * earth_cell / 2,
            earth_cell,
            earth_cell,
        ),
        body="earth",
        nodata=earth_nodata,
        valid_mask=earth_valid_mask,
    )
    return mars_path, mars_manifest, earth_path, earth_manifest, (lon, lat)


def make_observation_counts(
    path: Path,
    dem_path: Path,
    source_manifest: DatasetManifest,
    counts: np.ndarray,
) -> ObservationCountSource:
    with rasterio.open(dem_path) as dem:
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=dem.width,
            height=dem.height,
            count=1,
            dtype="uint8",
            crs=dem.crs,
            transform=dem.transform,
        ) as dataset:
            dataset.write(counts.astype("uint8"), 1)
        with rasterio.open(path) as dataset:
            bounds = (
                dataset.bounds.left,
                dataset.bounds.bottom,
                dataset.bounds.right,
                dataset.bounds.top,
            )
            resolution = dataset.res
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = ObservationCountsManifest(
        id=digest,
        checksum_sha256=digest,
        source_topography_id=source_manifest.id,
        provider="Documented analytical fixture",
        product="MOLA observation counts fixture",
        product_id="MEGC44N000HB",
        source_url="https://example.invalid/counts.img",
        label_source_url="https://example.invalid/counts.lbl",
        downloaded_at=datetime.now(UTC),
        file_size_bytes=path.stat().st_size,
        crs=source_manifest.crs,
        bounds=bounds,
        width=counts.shape[1],
        height=counts.shape[0],
        pixel_resolution_x=abs(resolution[0]),
        pixel_resolution_y=abs(resolution[1]),
        dtype="uint8",
        count_units="observations per source cell",
        zero_count_means_unobserved=True,
        total_cells=int(counts.size),
        observed_cells=int(np.count_nonzero(counts)),
        maximum_count=int(counts.max(initial=0)),
        label_checksum_sha256="a" * 64,
        attribution="Analytical test fixture only",
    )
    return ObservationCountSource(path, manifest)


def test_flat_surfaces_align_to_local_metric_common_support(tmp_path: Path) -> None:
    mars = np.full((64, 64), 125.0, dtype=np.float32)
    earth = np.full((160, 160), 340.0, dtype=np.float32)
    mars_path, mars_manifest, earth_path, earth_manifest, center = make_pair(tmp_path, mars, earth)

    result = run_scale_bridge(
        planetary_raster=mars_path,
        planetary_manifest=mars_manifest,
        planetary_center=center,
        earth_raster=earth_path,
        earth_manifest=earth_manifest,
        earth_center=center,
        support_width_m=4_000,
        support_height_m=4_000,
        output_dir=tmp_path / "out",
    )

    assert result.report.target_resolution_m == pytest.approx(100.0, abs=0.01)
    assert result.report.grid_width == result.report.grid_height == 40
    assert result.report.coverage.common_fraction == 1.0
    assert np.nanmax(np.abs(result.planetary_relative_elevation_m)) == 0.0
    assert np.nanmax(np.abs(result.earth_relative_elevation_m)) == 0.0
    assert result.planetary_local_crs != result.earth_local_crs
    assert (
        result.report.vertical_comparison
        == "relative terrain only; absolute elevations not compared"
    )
    assert result.common_support_mask.all()
    assert Path(result.artifact_paths["report"]).is_file()
    assert result.report.coverage.common_valid_area_m2 == pytest.approx(16_000_000)
    mars_to_local = Transformer.from_crs(
        MARS_CRS.geodetic_crs, result.planetary_local_crs, always_xy=True
    )
    earth_to_local = Transformer.from_crs("EPSG:4326", result.earth_local_crs, always_xy=True)
    assert mars_to_local.transform(*center) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert earth_to_local.transform(*center) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert set(result.report.artifact_sha256) == {"planetary", "earth", "common_mask"}


def test_independent_support_sizes_report_body_specific_coverage(tmp_path: Path) -> None:
    mars = np.full((64, 64), 125.0, dtype=np.float32)
    earth = np.full((160, 160), 340.0, dtype=np.float32)
    mars_path, mars_manifest, earth_path, earth_manifest, center = make_pair(tmp_path, mars, earth)
    result = run_scale_bridge(
        planetary_raster=mars_path,
        planetary_manifest=mars_manifest,
        planetary_center=center,
        earth_raster=earth_path,
        earth_manifest=earth_manifest,
        earth_center=center,
        support_width_m=2_000,
        support_height_m=2_000,
        planetary_support_width_m=1_000,
        planetary_support_height_m=1_000,
        output_dir=tmp_path / "asymmetric",
    )
    assert result.planetary_relative_elevation_m.shape == (10, 10)
    assert result.earth_relative_elevation_m.shape == (20, 20)
    assert result.common_support_mask is None
    assert result.report.coverage.planetary_fraction == 1.0
    assert result.report.coverage.earth_fraction == 1.0
    assert result.report.coverage.planetary_output_cells == 100
    assert result.report.coverage.output_cells == 400
    assert result.report.coverage.common_fraction is None
    assert set(result.report.artifact_sha256) == {"planetary", "earth"}


@pytest.mark.parametrize(
    ("surface", "check"),
    [
        ("slope", lambda values: values[20, 25] > values[20, 20]),
        ("hill", lambda values: values[20, 20] > values[0, 0]),
        ("bowl", lambda values: values[20, 20] < values[0, 0]),
        ("sinusoid", lambda values: np.nanmax(values) > 5 and np.nanmin(values) < -5),
    ],
)
def test_known_terrain_shapes_survive_coarsening(tmp_path: Path, surface: str, check) -> None:
    row_p, col_p = np.mgrid[:64, :64]
    x_p, y_p = (col_p - 31.5) * 100.0, (31.5 - row_p) * 100.0
    row_e, col_e = np.mgrid[:160, :160]
    x_e, y_e = (col_e - 79.5) * 30.0, (79.5 - row_e) * 30.0

    def function(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        if surface == "slope":
            return 0.04 * x + 0.02 * y
        if surface == "hill":
            return 80 * np.exp(-((x / 700) ** 2 + (y / 700) ** 2))
        if surface == "bowl":
            return -80 * np.exp(-((x / 700) ** 2 + (y / 700) ** 2))
        return 8 * np.sin(x / 350) + 7 * np.sin(y / 420)

    mars, earth = function(x_p, y_p), function(x_e, y_e)
    paths = make_pair(tmp_path, mars, earth)
    result = run_scale_bridge(
        planetary_raster=paths[0],
        planetary_manifest=paths[1],
        planetary_center=paths[4],
        earth_raster=paths[2],
        earth_manifest=paths[3],
        earth_center=paths[4],
        support_width_m=4_000,
        support_height_m=4_000,
        output_dir=tmp_path / "out",
    )
    assert check(result.planetary_relative_elevation_m)
    if surface == "slope":
        row = result.planetary_relative_elevation_m[20]
        column_gradient = np.nanmedian(np.diff(row) / result.report.target_resolution_m)
        assert column_gradient == pytest.approx(0.04 / np.cos(np.deg2rad(18.4)), abs=0.004)


def test_nodata_does_not_become_zero_and_is_excluded_from_common_support(
    tmp_path: Path,
) -> None:
    mars = np.full((64, 64), 20.0, dtype=np.float32)
    earth = np.full((160, 160), 200.0, dtype=np.float32)
    mars[24:40, 24:40] = -9999
    earth[60:100, 60:100] = -9999
    paths = make_pair(tmp_path, mars, earth)
    result = run_scale_bridge(
        planetary_raster=paths[0],
        planetary_manifest=paths[1],
        planetary_center=paths[4],
        earth_raster=paths[2],
        earth_manifest=paths[3],
        earth_center=paths[4],
        support_width_m=4_000,
        support_height_m=4_000,
        output_dir=tmp_path / "out",
    )
    assert 0 < result.report.coverage.common_fraction < 1
    assert np.isnan(result.planetary_relative_elevation_m).any()
    assert not np.any(result.planetary_relative_elevation_m == -9999)
    assert not result.common_support_mask.all()


def test_external_mask_without_nodata_sentinel_is_applied_to_values(tmp_path: Path) -> None:
    mars = np.full((4, 4), 5.0, dtype=np.float32)
    earth = np.full((200, 200), 10.0, dtype=np.float32)
    valid_mask = np.ones((200, 200), dtype=bool)
    valid_mask[100, 100] = False
    earth[100, 100] = 1_000_000
    paths = make_pair(
        tmp_path,
        mars,
        earth,
        earth_cell=1.0,
        earth_nodata=None,
        earth_valid_mask=valid_mask,
    )
    result = run_scale_bridge(
        planetary_raster=paths[0],
        planetary_manifest=paths[1],
        planetary_center=paths[4],
        earth_raster=paths[2],
        earth_manifest=paths[3],
        earth_center=paths[4],
        support_width_m=200,
        support_height_m=200,
        output_dir=tmp_path / "out",
    )
    assert result.report.earth.effective_resolution_m is None
    assert result.report.coverage.common_fraction == 1.0
    assert np.nanmax(np.abs(result.earth_relative_elevation_m)) == pytest.approx(0, abs=1e-6)


def test_requested_resolution_finer_than_source_is_coarsened_and_reported(tmp_path: Path) -> None:
    paths = make_pair(
        tmp_path,
        np.ones((64, 64), dtype=np.float32),
        np.ones((160, 160), dtype=np.float32),
    )
    result = run_scale_bridge(
        planetary_raster=paths[0],
        planetary_manifest=paths[1],
        planetary_center=paths[4],
        earth_raster=paths[2],
        earth_manifest=paths[3],
        earth_center=paths[4],
        support_width_m=2_000,
        support_height_m=2_000,
        target_resolution_m=50,
        output_dir=tmp_path / "out",
    )
    assert result.report.target_resolution_m == pytest.approx(100.0, abs=0.01)
    assert any(
        "finer than at least one source's measured sampling support" in item
        for item in result.report.warnings
    )


def test_large_requested_support_is_transparently_coarsened_to_cell_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = make_pair(
        tmp_path,
        np.ones((64, 64), dtype=np.float32),
        np.ones((64, 64), dtype=np.float32),
        mars_cell=30.0,
        earth_cell=30.0,
    )
    monkeypatch.setattr("app.engines.scale_bridge.engine.MAX_TARGET_CELLS", 400)
    result = run_scale_bridge(
        planetary_raster=paths[0],
        planetary_manifest=paths[1],
        planetary_center=paths[4],
        earth_raster=paths[2],
        earth_manifest=paths[3],
        earth_center=paths[4],
        support_width_m=1_500,
        support_height_m=1_500,
        planetary_support_width_m=1_500,
        planetary_support_height_m=1_500,
        target_resolution_m=30,
        output_dir=tmp_path / "budgeted",
    )
    assert result.report.target_resolution_m > 30
    assert result.report.grid_width * result.report.grid_height <= 400
    assert "target-cell budget" in result.report.target_resolution_basis
    assert any("transparently coarsened" in warning for warning in result.report.warnings)


def test_documented_effective_resolution_sets_a_coarser_comparison_floor(
    tmp_path: Path,
) -> None:
    paths = make_pair(
        tmp_path,
        np.ones((64, 64), dtype=np.float32),
        np.ones((160, 160), dtype=np.float32),
    )
    metadata = {**paths[1].product_metadata, "effective_resolution_m": 250.0}
    mars_manifest = paths[1].model_copy(update={"product_metadata": metadata})
    result = run_scale_bridge(
        planetary_raster=paths[0],
        planetary_manifest=mars_manifest,
        planetary_center=paths[4],
        earth_raster=paths[2],
        earth_manifest=paths[3],
        earth_center=paths[4],
        support_width_m=2_000,
        support_height_m=2_000,
        output_dir=tmp_path / "out",
    )
    assert result.report.planetary.effective_resolution_m == 250.0
    assert result.report.target_resolution_m == pytest.approx(250.0, abs=0.01)


def test_malformed_center_is_rejected_as_a_domain_error(tmp_path: Path) -> None:
    paths = make_pair(
        tmp_path,
        np.ones((64, 64), dtype=np.float32),
        np.ones((160, 160), dtype=np.float32),
    )
    with pytest.raises(CoordinateTransformationError, match="longitude/latitude pair"):
        run_scale_bridge(
            planetary_raster=paths[0],
            planetary_manifest=paths[1],
            planetary_center=(77.5,),  # type: ignore[arg-type]
            earth_raster=paths[2],
            earth_manifest=paths[3],
            earth_center=paths[4],
            support_width_m=2_000,
            support_height_m=2_000,
            output_dir=tmp_path / "out",
        )


def test_invalid_or_unparseable_crs_is_rejected(tmp_path: Path) -> None:
    paths = make_pair(
        tmp_path,
        np.ones((64, 64), dtype=np.float32),
        np.ones((160, 160), dtype=np.float32),
    )
    with pytest.raises(InvalidRasterError, match="inspect or transform"):
        run_scale_bridge(
            planetary_raster=paths[0],
            planetary_manifest=paths[1].model_copy(update={"crs": "not-a-coordinate-system"}),
            planetary_center=paths[4],
            earth_raster=paths[2],
            earth_manifest=paths[3],
            earth_center=paths[4],
            support_width_m=2_000,
            support_height_m=2_000,
            output_dir=tmp_path / "out",
        )


def test_manifest_mismatch_is_rejected_before_reprojection(tmp_path: Path) -> None:
    paths = make_pair(
        tmp_path,
        np.ones((64, 64), dtype=np.float32),
        np.ones((160, 160), dtype=np.float32),
    )
    altered_bounds = (paths[1].bounds[0] + 1, *paths[1].bounds[1:])
    with pytest.raises(InvalidRasterError, match="bounds differ"):
        run_scale_bridge(
            planetary_raster=paths[0],
            planetary_manifest=paths[1].model_copy(update={"bounds": altered_bounds}),
            planetary_center=paths[4],
            earth_raster=paths[2],
            earth_manifest=paths[3],
            earth_center=paths[4],
            support_width_m=2_000,
            support_height_m=2_000,
            output_dir=tmp_path / "out",
        )


def test_vertical_units_convert_to_metres_and_unknown_units_are_rejected(
    tmp_path: Path,
) -> None:
    paths = make_pair(
        tmp_path,
        np.full((64, 64), 2.0, dtype=np.float32),
        np.full((160, 160), 10.0, dtype=np.float32),
    )
    feet_manifest = paths[3].model_copy(update={"vertical_units": "feet"})
    result = run_scale_bridge(
        planetary_raster=paths[0],
        planetary_manifest=paths[1],
        planetary_center=paths[4],
        earth_raster=paths[2],
        earth_manifest=feet_manifest,
        earth_center=paths[4],
        support_width_m=2_000,
        support_height_m=2_000,
        output_dir=tmp_path / "out",
    )
    assert result.report.earth.relative_elevation_reference_m == pytest.approx(3.048)
    with pytest.raises(IncompatibleVerticalUnitsError, match="converted to metres"):
        run_scale_bridge(
            planetary_raster=paths[0],
            planetary_manifest=paths[1],
            planetary_center=paths[4],
            earth_raster=paths[2],
            earth_manifest=paths[3].model_copy(update={"vertical_units": "furlong"}),
            earth_center=paths[4],
            support_width_m=2_000,
            support_height_m=2_000,
            output_dir=tmp_path / "unsupported-units",
        )


def test_reproducibility_hash_is_stable_for_identical_input_and_configuration(
    tmp_path: Path,
) -> None:
    paths = make_pair(
        tmp_path,
        np.full((64, 64), 125.0, dtype=np.float32),
        np.full((160, 160), 340.0, dtype=np.float32),
    )
    kwargs = {
        "planetary_raster": paths[0],
        "planetary_manifest": paths[1],
        "planetary_center": paths[4],
        "earth_raster": paths[2],
        "earth_manifest": paths[3],
        "earth_center": paths[4],
        "support_width_m": 2_000,
        "support_height_m": 2_000,
        "output_dir": tmp_path / "out",
    }
    first = run_scale_bridge(**kwargs)
    second = run_scale_bridge(**kwargs)
    assert first.report.reproducibility_sha256 == second.report.reproducibility_sha256
    assert np.array_equal(first.common_support_mask, second.common_support_mask)
    assert np.allclose(
        first.planetary_relative_elevation_m, second.planetary_relative_elevation_m, equal_nan=True
    )


def test_mola_zero_count_cells_are_excluded_without_count_weighting(tmp_path: Path) -> None:
    mars = np.full((64, 64), 10.0, dtype=np.float32)
    mars[28:36, 28:36] = 10_000.0
    earth = np.full((160, 160), 50.0, dtype=np.float32)
    paths = make_pair(tmp_path, mars, earth)
    paths = (
        paths[0],
        paths[1].model_copy(update={"product_metadata": {"product_id": "MEGT44N000HB"}}),
        *paths[2:],
    )
    counts = np.ones((64, 64), dtype=np.uint8)
    counts[28:36, 28:36] = 0
    count_source = make_observation_counts(tmp_path / "mola-counts.tif", paths[0], paths[1], counts)
    kwargs = {
        "planetary_raster": paths[0],
        "planetary_manifest": paths[1],
        "planetary_center": paths[4],
        "earth_raster": paths[2],
        "earth_manifest": paths[3],
        "earth_center": paths[4],
        "support_width_m": 2_000,
        "support_height_m": 2_000,
        "output_dir": tmp_path / "out",
        "planetary_observation_counts": count_source,
    }
    result = run_scale_bridge(**kwargs)
    assert result.report.planetary_observation_counts is not None
    assert (
        "count magnitude is not used"
        in result.report.planetary_observation_counts.zero_count_policy
    )
    assert result.report.coverage.planetary_fraction < 1.0
    assert result.report.coverage.common_fraction < 1.0
    assert np.nanmax(np.abs(result.planetary_relative_elevation_m)) == pytest.approx(0.0)
    repeated = run_scale_bridge(**kwargs)
    assert result.report.reproducibility_sha256 == repeated.report.reproducibility_sha256
    assert any(
        "MOLA observation-count raster was not supplied" in w
        for w in run_scale_bridge(
            **{
                **kwargs,
                "output_dir": tmp_path / "without-counts",
                "planetary_observation_counts": None,
            }
        ).report.warnings
    )

    positive_counts = counts.copy()
    positive_counts[positive_counts > 0] = 255
    weighted_variant = make_observation_counts(
        tmp_path / "mola-counts-255.tif", paths[0], paths[1], positive_counts
    )
    second = run_scale_bridge(
        **{
            **kwargs,
            "output_dir": tmp_path / "count-variant",
            "planetary_observation_counts": weighted_variant,
        }
    )
    assert np.array_equal(result.common_support_mask, second.common_support_mask)
    assert np.allclose(
        result.planetary_relative_elevation_m,
        second.planetary_relative_elevation_m,
        equal_nan=True,
    )
    assert result.report.reproducibility_sha256 != second.report.reproducibility_sha256


def test_observation_count_wrong_provenance_and_checksum_are_rejected(tmp_path: Path) -> None:
    paths = make_pair(
        tmp_path,
        np.full((64, 64), 10.0, dtype=np.float32),
        np.full((160, 160), 20.0, dtype=np.float32),
    )
    counts = make_observation_counts(
        tmp_path / "counts.tif", paths[0], paths[1], np.ones((64, 64), dtype=np.uint8)
    )
    kwargs = {
        "planetary_raster": paths[0],
        "planetary_manifest": paths[1],
        "planetary_center": paths[4],
        "earth_raster": paths[2],
        "earth_manifest": paths[3],
        "earth_center": paths[4],
        "support_width_m": 2_000,
        "support_height_m": 2_000,
        "output_dir": tmp_path / "out",
    }
    wrong_source = counts.manifest.model_copy(update={"source_topography_id": "b" * 64})
    with pytest.raises(InvalidRasterError, match="different DEM"):
        run_scale_bridge(
            **kwargs,
            planetary_observation_counts=ObservationCountSource(counts.raster_path, wrong_source),
        )
    altered = counts.raster_path.read_bytes() + b"tamper"
    counts.raster_path.write_bytes(altered)
    with pytest.raises(InvalidRasterError, match="checksum"):
        run_scale_bridge(**kwargs, planetary_observation_counts=counts)


def test_observation_count_manifest_grid_mismatch_is_rejected(tmp_path: Path) -> None:
    paths = make_pair(
        tmp_path,
        np.full((64, 64), 10.0, dtype=np.float32),
        np.full((160, 160), 20.0, dtype=np.float32),
    )
    counts = make_observation_counts(
        tmp_path / "counts.tif", paths[0], paths[1], np.ones((64, 64), dtype=np.uint8)
    )
    shifted_bounds = (
        counts.manifest.bounds[0] + 1.0,
        *counts.manifest.bounds[1:],
    )
    bad_manifest = counts.manifest.model_copy(update={"bounds": shifted_bounds})
    with pytest.raises(InvalidRasterError, match="co-registered"):
        run_scale_bridge(
            planetary_raster=paths[0],
            planetary_manifest=paths[1],
            planetary_center=paths[4],
            earth_raster=paths[2],
            earth_manifest=paths[3],
            earth_center=paths[4],
            support_width_m=2_000,
            support_height_m=2_000,
            output_dir=tmp_path / "out",
            planetary_observation_counts=ObservationCountSource(counts.raster_path, bad_manifest),
        )


def test_observation_count_summary_must_match_raster(tmp_path: Path) -> None:
    paths = make_pair(
        tmp_path,
        np.full((64, 64), 10.0, dtype=np.float32),
        np.full((160, 160), 20.0, dtype=np.float32),
    )
    counts = make_observation_counts(
        tmp_path / "counts.tif", paths[0], paths[1], np.ones((64, 64), dtype=np.uint8)
    )
    bad_manifest = counts.manifest.model_copy(update={"observed_cells": 1})
    with pytest.raises(InvalidRasterError, match="summary metadata"):
        run_scale_bridge(
            planetary_raster=paths[0],
            planetary_manifest=paths[1],
            planetary_center=paths[4],
            earth_raster=paths[2],
            earth_manifest=paths[3],
            earth_center=paths[4],
            support_width_m=2_000,
            support_height_m=2_000,
            output_dir=tmp_path / "out",
            planetary_observation_counts=ObservationCountSource(counts.raster_path, bad_manifest),
        )
