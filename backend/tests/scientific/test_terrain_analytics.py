"""Behavior checks for the public terrain-analytics raster pipeline."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.core.exceptions import InvalidRasterError
from app.domain.schemas.terrain_analytics import TerrainAnalyticsConfig
from app.engines.terrain_analytics.engine import (
    analyze_terrain_raster,
    calculate_local_relief,
    calculate_plan_curvature,
    calculate_profile_curvature,
    calculate_slope_degrees,
    calculate_terrain_roughness,
    calculate_topographic_position_index,
    classify_relative_landform,
)


def source_dem(
    path: Path,
    values: np.ndarray,
    cell_size: float = 10.0,
    *,
    crs: str = "EPSG:32643",
    vertical_units: str | None = "m",
) -> Path:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype="float32",
        crs=crs,
        transform=from_origin(500_000, 2_000_000, cell_size, cell_size),
        nodata=-9999.0,
    ) as dataset:
        dataset.write(values.astype("float32"), 1)
        tags = dict(
            dataset_id="a" * 64,
            target_body="earth",
            product="Analytical test surface",
            source_sha256="b" * 64,
            value_semantics="test-only elevation surface",
        )
        if vertical_units is not None:
            tags["output_vertical_units"] = vertical_units
        dataset.update_tags(**tags)
    return path


def test_flat_surface_has_zero_slope_and_writes_a_georeferenced_map(tmp_path: Path) -> None:
    dem_path = source_dem(tmp_path / "flat.tif", np.full((21, 21), 42.0))
    result = analyze_terrain_raster(
        dem_path,
        tmp_path / "features",
        TerrainAnalyticsConfig(neighborhood_radius_m=20),
    )

    slope = result.report.features["slope"]
    with rasterio.open(dem_path) as source:
        source_transform = source.transform
    with rasterio.open(result.feature_paths["slope"]) as dataset:
        values = dataset.read(1, masked=True)
        assert dataset.crs.to_epsg() == 32643
        assert dataset.transform == source_transform
    assert np.ma.count(values) > 0
    assert np.ma.max(values) == 0.0
    assert slope.units == "degree"
    assert slope.summary.mean == 0.0
    assert set(result.report.features) == {
        "slope",
        "local_relief",
        "terrain_roughness",
        "profile_curvature",
        "plan_curvature",
        "topographic_position_index",
        "landform_morphology",
    }


def test_horn_slope_matches_analytic_plane_and_map_units_are_degrees(tmp_path: Path) -> None:
    cell = 10.0
    rows, columns = np.mgrid[:31, :31]
    x = columns * cell
    y = -rows * cell
    elevation = 0.3 * x + 0.4 * y
    dem_path = source_dem(tmp_path / "plane.tif", elevation, cell)
    result = analyze_terrain_raster(
        dem_path,
        tmp_path / "features",
        TerrainAnalyticsConfig(neighborhood_radius_m=10),
    )

    with rasterio.open(result.feature_paths["slope"]) as dataset:
        slope = dataset.read(1, masked=True)
    assert np.ma.max(np.abs(slope[1:-1, 1:-1] - np.degrees(np.arctan(0.5)))) < 1e-5
    assert result.report.features["slope"].summary.valid_sample_count == 29 * 29


def test_local_relief_roughness_and_tpi_match_independent_window_calculations(
    tmp_path: Path,
) -> None:
    cell = 10.0
    rows, columns = np.mgrid[:21, :21]
    values = 0.3 * columns * cell - 0.4 * rows * cell
    dem_path = source_dem(tmp_path / "plane.tif", values, cell)
    result = analyze_terrain_raster(
        dem_path,
        tmp_path / "features",
        TerrainAnalyticsConfig(neighborhood_radius_m=10),
    )
    center = (10, 10)
    window = values[9:12, 9:12]

    with rasterio.open(result.feature_paths["local_relief"]) as dataset:
        relief = dataset.read(1, masked=True)
    with rasterio.open(result.feature_paths["terrain_roughness"]) as dataset:
        roughness = dataset.read(1, masked=True)
    with rasterio.open(result.feature_paths["topographic_position_index"]) as dataset:
        tpi = dataset.read(1, masked=True)
    assert relief[center] == pytest.approx(np.max(window) - np.min(window))
    assert roughness[center] == pytest.approx(np.std(window, ddof=0))
    assert tpi[center] == pytest.approx(values[center] - np.mean(window))
    assert result.report.features["local_relief"].window_cells == (3, 3)
    assert result.report.features["local_relief"].window_support_m == (30.0, 30.0)


def test_curvature_sign_and_value_match_quadratic_reference(tmp_path: Path) -> None:
    cell = 10.0
    rows, columns = np.mgrid[:31, :31]
    x = (columns - 15) * cell
    y = -(rows - 15) * cell
    p0, q0, r0, t0, s0 = 0.5, 0.2, -0.02, -0.04, 0.005
    elevation = 0.5 * r0 * x * x + s0 * x * y + 0.5 * t0 * y * y + p0 * x + q0 * y
    dem_path = source_dem(tmp_path / "quadratic.tif", elevation, cell)
    result = analyze_terrain_raster(
        dem_path,
        tmp_path / "features",
        TerrainAnalyticsConfig(neighborhood_radius_m=10),
    )
    center = (15, 15)
    gradient_squared = p0 * p0 + q0 * q0
    reference_profile = (r0 * p0 * p0 + 2 * s0 * p0 * q0 + t0 * q0 * q0) / (
        gradient_squared * (1 + gradient_squared) ** 1.5
    )
    reference_plan = -(r0 * q0 * q0 - 2 * s0 * p0 * q0 + t0 * p0 * p0) / gradient_squared**1.5
    with rasterio.open(result.feature_paths["profile_curvature"]) as dataset:
        profile = dataset.read(1, masked=True)
    with rasterio.open(result.feature_paths["plan_curvature"]) as dataset:
        plan = dataset.read(1, masked=True)
    assert profile[center] == pytest.approx(reference_profile, abs=1e-7)
    assert plan[center] == pytest.approx(reference_plan, abs=1e-7)
    assert profile[center] < 0
    assert plan[center] > 0


def test_nodata_holes_and_raster_edges_reduce_feature_coverage(tmp_path: Path) -> None:
    values = np.full((21, 21), 0.0, dtype=np.float32)
    values[10, 10] = -9999
    dem_path = source_dem(tmp_path / "nodata-hole.tif", values)
    result = analyze_terrain_raster(
        dem_path,
        tmp_path / "features",
        TerrainAnalyticsConfig(neighborhood_radius_m=10),
    )
    with rasterio.open(result.feature_paths["slope"]) as dataset:
        slope = dataset.read(1, masked=True)
    with rasterio.open(result.feature_paths["topographic_position_index"]) as dataset:
        tpi = dataset.read(1, masked=True)
    assert np.ma.getmaskarray(slope)[10, 10]
    assert np.ma.getmaskarray(slope)[9:12, 9:12].all()
    assert np.ma.getmaskarray(slope)[0, :].all()
    assert np.ma.getmaskarray(tpi)[10, 10]
    assert result.report.features["slope"].coverage_of_raster < 1
    assert result.report.features["topographic_position_index"].coverage_of_raster < 1


def test_slope_is_invariant_across_input_postings_for_same_plane(tmp_path: Path) -> None:
    results = []
    for cell in (10.0, 25.0):
        rows, columns = np.mgrid[:41, :41]
        values = 0.2 * columns * cell - 0.3 * rows * cell
        path = source_dem(tmp_path / f"plane-{int(cell)}.tif", values, cell)
        result = analyze_terrain_raster(
            path,
            tmp_path / f"features-{int(cell)}",
            TerrainAnalyticsConfig(neighborhood_radius_m=50),
        )
        with rasterio.open(result.feature_paths["slope"]) as dataset:
            results.append(dataset.read(1, masked=True))
    expected = np.degrees(np.arctan(np.hypot(0.2, 0.3)))
    assert np.ma.max(np.abs(results[0].compressed() - expected)) < 1e-5
    assert np.ma.max(np.abs(results[1].compressed() - expected)) < 1e-5


def test_landform_map_is_relative_tpi_classification_not_material(tmp_path: Path) -> None:
    rows, columns = np.mgrid[:41, :41]
    hill = 30 * np.exp(-((columns - 20) ** 2 + (rows - 20) ** 2) / 35)
    dem_path = source_dem(tmp_path / "hill.tif", hill)
    result = analyze_terrain_raster(
        dem_path,
        tmp_path / "features",
        TerrainAnalyticsConfig(neighborhood_radius_m=10),
    )
    with rasterio.open(result.feature_paths["landform_morphology"]) as dataset:
        classes = dataset.read(1, masked=True)
    assert classes[20, 20] == 1
    assert set(np.unique(classes.compressed())).issubset({-1, 0, 1})
    assert "material" in result.report.features["landform_morphology"].aggregation


def test_flat_reference_marks_landform_morphology_unavailable(tmp_path: Path) -> None:
    path = source_dem(tmp_path / "flat-reference.tif", np.full((9, 9), 12.0))
    result = analyze_terrain_raster(
        path,
        tmp_path / "flat-features",
        TerrainAnalyticsConfig(neighborhood_radius_m=10),
    )

    feature = result.report.features["landform_morphology"]
    assert feature.normalization_scale_m is None
    assert feature.valid_sample_count == 0
    assert any(
        "Landform morphology is unavailable" in warning for warning in result.report.warnings
    )
    with rasterio.open(result.feature_paths["landform_morphology"]) as dataset:
        assert dataset.tags()["normalization_scale_status"] == "unavailable"
        assert "normalization_scale_m" not in dataset.tags()
        assert dataset.read(1, masked=True).count() == 0


def test_disabled_landform_scale_does_not_reestimate_candidate_scale(tmp_path: Path) -> None:
    rows, columns = np.mgrid[:21, :21]
    path = source_dem(tmp_path / "candidate.tif", columns.astype(float) * 10)
    result = analyze_terrain_raster(
        path,
        tmp_path / "candidate-features",
        TerrainAnalyticsConfig(
            neighborhood_radius_m=10,
            landform_morphology_enabled=False,
        ),
    )
    feature = result.report.features["landform_morphology"]
    assert feature.normalization_scale_m is None
    assert feature.valid_sample_count == 0


def test_shared_landform_scale_keeps_a_cell_class_stable_when_context_changes() -> None:
    local = np.array([[0.0, 0.0, 1.0]])
    expanded = np.concatenate((local, np.full((1, 100), 10.0)), axis=1)
    shared_scale = 0.5
    assert classify_relative_landform(local, shared_scale)[0, 2] == 1
    assert classify_relative_landform(expanded, shared_scale)[0, 2] == 1


def test_landform_own_raster_scale_example_exposes_context_dependence() -> None:
    local = np.array([[0.0, 0.0, 1.0]])
    expanded = np.concatenate((local, np.full((1, 100), 10.0)), axis=1)
    assert classify_relative_landform(local)[0, 2] == 1
    assert classify_relative_landform(expanded)[0, 2] == 0


@pytest.mark.parametrize(("sign", "expected"), [(1.0, 1), (-1.0, -1)])
def test_gaussian_ridge_and_valley_tpi_polarity(tmp_path: Path, sign: float, expected: int) -> None:
    rows, _ = np.mgrid[:41, :41]
    profile = sign * 40 * np.exp(-((rows - 20) ** 2) / 18)
    values = np.broadcast_to(profile, (41, 41)).copy()
    path = source_dem(tmp_path / f"ridge-valley-{sign}.tif", values)
    result = analyze_terrain_raster(
        path,
        tmp_path / f"features-{sign}",
        TerrainAnalyticsConfig(neighborhood_radius_m=10),
    )
    with rasterio.open(result.feature_paths["topographic_position_index"]) as dataset:
        tpi = dataset.read(1, masked=True)
    assert tpi[20, 20] * expected > 0


def test_independent_algorithm_interfaces_return_expected_units_and_values() -> None:
    rows, columns = np.mgrid[:9, :9]
    elevation = columns.astype("float64") + 2 * rows
    valid = np.ones(elevation.shape, dtype=bool)
    slope = calculate_slope_degrees(elevation, valid, 1.0, 1.0)
    relief = calculate_local_relief(elevation, valid, (3, 3), 1.0)
    roughness = calculate_terrain_roughness(elevation, valid, (3, 3), 1.0)
    profile = calculate_profile_curvature(elevation, valid, 1.0, 1.0)
    plan = calculate_plan_curvature(elevation, valid, 1.0, 1.0)
    tpi = calculate_topographic_position_index(elevation, valid, (3, 3), 1.0)
    classes = classify_relative_landform(tpi)

    assert slope[4, 4] == pytest.approx(np.degrees(np.arctan(np.sqrt(5))))
    assert relief[4, 4] == pytest.approx(6.0)
    assert roughness[4, 4] == pytest.approx(np.std(elevation[3:6, 3:6], ddof=0))
    assert profile[4, 4] == pytest.approx(0.0)
    assert plan[4, 4] == pytest.approx(0.0)
    assert tpi[4, 4] == pytest.approx(0.0)
    assert classes[4, 4] == 0


def test_geographic_crs_and_unknown_vertical_units_are_rejected(tmp_path: Path) -> None:
    values = np.ones((11, 11), dtype=np.float32)
    geographic = source_dem(tmp_path / "geographic.tif", values, crs="EPSG:4326")
    with pytest.raises(InvalidRasterError, match="projected metric CRS"):
        analyze_terrain_raster(geographic, tmp_path / "geographic-features")

    unknown_vertical = source_dem(tmp_path / "unknown-vertical.tif", values, vertical_units=None)
    with pytest.raises(InvalidRasterError, match="vertical units"):
        analyze_terrain_raster(unknown_vertical, tmp_path / "unknown-features")


def test_all_nodata_surface_is_rejected_without_zero_filling(tmp_path: Path) -> None:
    values = np.full((11, 11), -9999.0, dtype=np.float32)
    dem_path = source_dem(tmp_path / "all-nodata.tif", values)
    with pytest.raises(InvalidRasterError, match="no valid elevations"):
        analyze_terrain_raster(dem_path, tmp_path / "features")


def test_projected_us_survey_foot_pixels_convert_to_metric_gradient(tmp_path: Path) -> None:
    rows, columns = np.mgrid[:21, :21]
    values = columns.astype("float64")
    dem_path = source_dem(
        tmp_path / "feet-crs.tif",
        values,
        cell_size=10.0,
        crs="EPSG:2263",
    )
    result = analyze_terrain_raster(
        dem_path,
        tmp_path / "features",
        TerrainAnalyticsConfig(neighborhood_radius_m=3),
    )
    with rasterio.open(result.feature_paths["slope"]) as dataset:
        slope = dataset.read(1, masked=True)
    expected = np.degrees(np.arctan(1 / (10 * 1200 / 3937)))
    assert result.report.pixel_width_m == pytest.approx(10 * 1200 / 3937)
    assert slope[10, 10] == pytest.approx(expected, abs=1e-5)
