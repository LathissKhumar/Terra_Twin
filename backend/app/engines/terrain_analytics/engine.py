"""Deterministic terrain derivatives for validated metric ScaleBridge rasters."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import pyproj
import rasterio
import scipy
from scipy import ndimage

from app.core.exceptions import InvalidRasterError
from app.domain.schemas.terrain_analytics import (
    CategoricalFeatureSummary,
    FeatureMapReport,
    HistogramSummary,
    NumericFeatureSummary,
    TerrainAnalyticsConfig,
    TerrainAnalyticsReport,
    TerrainAnalyticsResult,
)
from app.engines.data_ingestion.ingestion import sha256_file

OUTPUT_NODATA = np.float32(-3.402823466e38)
MAX_ANALYTICS_CELLS = 4_000_000
MIN_PROFILE_SAMPLES_FOR_WARNING = 20
_UNIT_TO_METRES = {
    "m": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "metre": 1.0,
    "metres": 1.0,
    "km": 1_000.0,
    "kilometer": 1_000.0,
    "kilometers": 1_000.0,
    "kilometre": 1_000.0,
    "kilometres": 1_000.0,
    "ft": 0.3048,
    "foot": 0.3048,
    "feet": 0.3048,
}
_LANDFORM_NAMES = {-1: "relative_low", 0: "near_local_mean", 1: "relative_high"}
FeatureDefinition = tuple[
    str,
    str,
    str,
    tuple[int, int] | None,
    tuple[float, float] | None,
    str,
    str,
    str,
]


def _linear_unit_factor(unit: str, axis: str) -> float:
    factor = _UNIT_TO_METRES.get(unit.strip().casefold())
    if factor is None:
        raise InvalidRasterError(f"Unsupported {axis} units for terrain analysis")
    return factor


def _window_size(radius_m: float, spacing_x_m: float, spacing_y_m: float) -> tuple[int, int]:
    radius_x = max(1, math.ceil(radius_m / spacing_x_m))
    radius_y = max(1, math.ceil(radius_m / spacing_y_m))
    if radius_x > 50 or radius_y > 50:
        raise InvalidRasterError("Configured terrain neighborhood exceeds the 101-cell limit")
    return 2 * radius_y + 1, 2 * radius_x + 1


def _strict_3x3(valid: np.ndarray) -> np.ndarray:
    filtered = ndimage.minimum_filter(valid.astype("uint8"), size=(3, 3), mode="constant", cval=0)
    return cast(np.ndarray, filtered).astype(bool)


def _horn_slope(elevation: np.ndarray, valid: np.ndarray, dx: float, dy: float) -> np.ndarray:
    output = np.full(elevation.shape, np.nan, dtype="float64")
    neighborhoods = _strict_3x3(valid)
    z = np.where(valid, elevation, 0.0)
    east = (
        z[:-2, 2:] + 2 * z[1:-1, 2:] + z[2:, 2:] - z[:-2, :-2] - 2 * z[1:-1, :-2] - z[2:, :-2]
    ) / (8 * dx)
    north = (
        z[:-2, :-2] + 2 * z[:-2, 1:-1] + z[:-2, 2:] - z[2:, :-2] - 2 * z[2:, 1:-1] - z[2:, 2:]
    ) / (8 * dy)
    center_valid = neighborhoods[1:-1, 1:-1]
    output[1:-1, 1:-1][center_valid] = np.degrees(
        np.arctan(np.hypot(east[center_valid], north[center_valid]))
    )
    return output


def _curvatures(
    elevation: np.ndarray, valid: np.ndarray, dx: float, dy: float
) -> tuple[np.ndarray, np.ndarray]:
    profile = np.full(elevation.shape, np.nan, dtype="float64")
    plan = np.full(elevation.shape, np.nan, dtype="float64")
    neighborhoods = _strict_3x3(valid)
    z = np.where(valid, elevation, 0.0)
    center = z[1:-1, 1:-1]
    northwest, north, northeast = z[:-2, :-2], z[:-2, 1:-1], z[:-2, 2:]
    southwest, south, southeast = z[2:, :-2], z[2:, 1:-1], z[2:, 2:]
    west, east = z[1:-1, :-2], z[1:-1, 2:]

    p = (east - west) / (2 * dx)
    q = (north - south) / (2 * dy)
    r = (east - 2 * center + west) / (dx * dx)
    t = (north - 2 * center + south) / (dy * dy)
    s = (northeast - northwest - southeast + southwest) / (4 * dx * dy)
    gradient_squared = p * p + q * q
    neighborhood_valid = neighborhoods[1:-1, 1:-1]
    flat = (
        (gradient_squared <= 1e-20)
        & (np.abs(r) <= 1e-20)
        & (np.abs(s) <= 1e-20)
        & (np.abs(t) <= 1e-20)
    )
    calculable = neighborhood_valid & (gradient_squared > 1e-20)
    profile_local = np.full(gradient_squared.shape, np.nan, dtype="float64")
    plan_local = np.full(gradient_squared.shape, np.nan, dtype="float64")
    profile_local[calculable] = (
        r[calculable] * p[calculable] ** 2
        + 2 * s[calculable] * p[calculable] * q[calculable]
        + t[calculable] * q[calculable] ** 2
    ) / (gradient_squared[calculable] * (1 + gradient_squared[calculable]) ** 1.5)
    plan_local[calculable] = (
        -r[calculable] * q[calculable] ** 2
        + 2 * s[calculable] * p[calculable] * q[calculable]
        - t[calculable] * p[calculable] ** 2
    ) / gradient_squared[calculable] ** 1.5
    profile_local[neighborhood_valid & flat] = 0.0
    plan_local[neighborhood_valid & flat] = 0.0
    profile[1:-1, 1:-1] = profile_local
    plan[1:-1, 1:-1] = plan_local
    return profile, plan


def _focal_features(
    elevation: np.ndarray,
    valid: np.ndarray,
    window: tuple[int, int],
    minimum_fraction: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    size = window[0] * window[1]
    valid_float = valid.astype("float64")
    count = np.rint(ndimage.uniform_filter(valid_float, size=window, mode="constant") * size)
    required = math.ceil(minimum_fraction * size)
    output_valid = valid & (count >= required)
    values = np.where(valid, elevation, 0.0)
    sum_values = ndimage.uniform_filter(values, size=window, mode="constant") * size
    sum_squares = ndimage.uniform_filter(values * values, size=window, mode="constant") * size
    mean = np.divide(sum_values, count, out=np.zeros_like(sum_values), where=count > 0)
    variance = np.divide(sum_squares, count, out=np.zeros_like(sum_squares), where=count > 0)
    variance = np.maximum(variance - mean * mean, 0.0)
    roughness = np.full(elevation.shape, np.nan, dtype="float64")
    roughness[output_valid] = np.sqrt(variance[output_valid])
    tpi = np.full(elevation.shape, np.nan, dtype="float64")
    tpi[output_valid] = elevation[output_valid] - mean[output_valid]

    maximum = ndimage.maximum_filter(
        np.where(valid, elevation, -np.inf), size=window, mode="constant", cval=-np.inf
    )
    minimum = ndimage.minimum_filter(
        np.where(valid, elevation, np.inf), size=window, mode="constant", cval=np.inf
    )
    relief = np.full(elevation.shape, np.nan, dtype="float64")
    relief[output_valid] = maximum[output_valid] - minimum[output_valid]
    return relief, roughness, tpi


def _validate_surface(elevation: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    surface = np.asarray(elevation, dtype="float64")
    mask = np.asarray(valid, dtype=bool)
    if surface.ndim != 2 or surface.shape != mask.shape:
        raise ValueError("Elevation and validity mask must be same-shaped 2D arrays")
    if min(surface.shape) < 3:
        raise ValueError("Terrain algorithms require at least a 3x3 surface")
    if not np.isfinite(surface[mask]).all():
        raise ValueError("Valid elevations must be finite")
    return surface, mask & np.isfinite(surface)


def _validate_spacing(pixel_width_m: float, pixel_height_m: float) -> None:
    if not all(math.isfinite(value) and value > 0 for value in (pixel_width_m, pixel_height_m)):
        raise ValueError("Pixel dimensions must be positive finite metres")


def _validate_focal_parameters(
    window_shape: tuple[int, int], minimum_valid_fraction: float
) -> None:
    if (
        len(window_shape) != 2
        or min(window_shape) <= 0
        or any(size % 2 == 0 for size in window_shape)
    ):
        raise ValueError("Focal window dimensions must be positive odd integers")
    if not math.isfinite(minimum_valid_fraction) or not 0.5 <= minimum_valid_fraction <= 1:
        raise ValueError("Minimum valid fraction must be finite and between 0.5 and 1")


def calculate_slope_degrees(
    elevation_m: np.ndarray,
    valid_mask: np.ndarray,
    pixel_width_m: float,
    pixel_height_m: float,
) -> np.ndarray:
    """Return Horn 3x3 gradient magnitude in degrees; edge/NoData stencils stay missing."""
    surface, valid = _validate_surface(elevation_m, valid_mask)
    _validate_spacing(pixel_width_m, pixel_height_m)
    return _horn_slope(surface, valid, pixel_width_m, pixel_height_m)


def calculate_local_relief(
    elevation_m: np.ndarray,
    valid_mask: np.ndarray,
    window_shape: tuple[int, int],
    minimum_valid_fraction: float = 0.8,
) -> np.ndarray:
    """Return focal maximum-minus-minimum relief in metres."""
    surface, valid = _validate_surface(elevation_m, valid_mask)
    _validate_focal_parameters(window_shape, minimum_valid_fraction)
    return _focal_features(surface, valid, window_shape, minimum_valid_fraction)[0]


def calculate_terrain_roughness(
    elevation_m: np.ndarray,
    valid_mask: np.ndarray,
    window_shape: tuple[int, int],
    minimum_valid_fraction: float = 0.8,
) -> np.ndarray:
    """Return population elevation standard deviation in metres, not vector ruggedness."""
    surface, valid = _validate_surface(elevation_m, valid_mask)
    _validate_focal_parameters(window_shape, minimum_valid_fraction)
    return _focal_features(surface, valid, window_shape, minimum_valid_fraction)[1]


def calculate_profile_curvature(
    elevation_m: np.ndarray,
    valid_mask: np.ndarray,
    pixel_width_m: float,
    pixel_height_m: float,
) -> np.ndarray:
    """Return slope-line directional curvature in inverse metres; convex is negative."""
    surface, valid = _validate_surface(elevation_m, valid_mask)
    _validate_spacing(pixel_width_m, pixel_height_m)
    return _curvatures(surface, valid, pixel_width_m, pixel_height_m)[0]


def calculate_plan_curvature(
    elevation_m: np.ndarray,
    valid_mask: np.ndarray,
    pixel_width_m: float,
    pixel_height_m: float,
) -> np.ndarray:
    """Return cross-slope directional curvature in inverse metres; convex is positive."""
    surface, valid = _validate_surface(elevation_m, valid_mask)
    _validate_spacing(pixel_width_m, pixel_height_m)
    return _curvatures(surface, valid, pixel_width_m, pixel_height_m)[1]


def calculate_topographic_position_index(
    elevation_m: np.ndarray,
    valid_mask: np.ndarray,
    window_shape: tuple[int, int],
    minimum_valid_fraction: float = 0.8,
) -> np.ndarray:
    """Return center elevation minus neighborhood mean in metres; center is included."""
    surface, valid = _validate_surface(elevation_m, valid_mask)
    _validate_focal_parameters(window_shape, minimum_valid_fraction)
    return _focal_features(surface, valid, window_shape, minimum_valid_fraction)[2]


def classify_relative_landform(
    tpi_m: np.ndarray, standardization_scale_m: float | None = None
) -> np.ndarray:
    """Classify TPI at +/- one shared physical scale, defaulting to this raster's SD.

    Cross-region comparisons must pass the same reference-derived scale to every
    raster. The default remains useful for standalone descriptive maps only.
    """
    tpi = np.asarray(tpi_m, dtype="float64")
    if tpi.ndim != 2:
        raise ValueError("TPI input must be a 2D raster")
    valid = np.isfinite(tpi)
    classes = np.full(tpi.shape, np.nan, dtype="float64")
    if not valid.any():
        return classes
    tpi_standard_deviation = (
        float(np.std(tpi[valid], ddof=0))
        if standardization_scale_m is None
        else float(standardization_scale_m)
    )
    if not math.isfinite(tpi_standard_deviation) or tpi_standard_deviation < 0:
        raise ValueError("TPI standardization scale must be finite and nonnegative")
    if tpi_standard_deviation == 0:
        classes[valid] = 0
    else:
        standardized = tpi[valid] / tpi_standard_deviation
        classes[valid] = np.where(standardized > 1.0, 1, np.where(standardized < -1.0, -1, 0))
    return classes


def _numeric_summary(values: np.ndarray, bins: int) -> NumericFeatureSummary:
    valid = values[np.isfinite(values)]
    if valid.size == 0:
        return NumericFeatureSummary(
            valid_sample_count=0,
            histogram=HistogramSummary(bin_edges=[], counts=[]),
        )
    lower, upper = float(np.min(valid)), float(np.max(valid))
    if upper - lower <= max(1e-12, abs((upper + lower) / 2) * 1e-12):
        center = (upper + lower) / 2
        half_width = max(1e-6, abs(center) * 1e-6)
        edges = np.linspace(center - half_width, center + half_width, bins + 1)
    else:
        edges = np.linspace(lower, upper, bins + 1)
    counts, edges = np.histogram(valid, bins=edges)
    return NumericFeatureSummary(
        valid_sample_count=int(valid.size),
        mean=float(np.mean(valid)),
        median=float(np.median(valid)),
        standard_deviation=float(np.std(valid, ddof=0)),
        minimum=float(np.min(valid)),
        maximum=float(np.max(valid)),
        percentile_05=float(np.percentile(valid, 5)),
        percentile_25=float(np.percentile(valid, 25)),
        percentile_75=float(np.percentile(valid, 75)),
        percentile_95=float(np.percentile(valid, 95)),
        histogram=HistogramSummary(
            bin_edges=[float(edge) for edge in edges],
            counts=[int(count) for count in counts],
        ),
    )


def _write_feature(
    path: Path,
    values: np.ndarray,
    *,
    source_profile: dict[str, Any],
    tags: dict[str, str],
) -> None:
    encoded = np.where(np.isfinite(values), values, OUTPUT_NODATA).astype("float32")
    profile = {
        **source_profile,
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "nodata": float(OUTPUT_NODATA),
        "compress": "deflate",
        "predictor": 3,
    }
    profile.pop("blockxsize", None)
    profile.pop("blockysize", None)
    with rasterio.open(path, "w", **profile) as dataset:
        dataset.write(encoded, 1)
        dataset.update_tags(**tags)


def _feature_report(
    name: str,
    algorithm: str,
    units: str,
    values: np.ndarray,
    output_path: Path,
    input_valid_count: int,
    raster_cell_count: int,
    bins: int,
    *,
    window: tuple[int, int] | None = None,
    window_support_m: tuple[float, float] | None = None,
    edge_policy: str,
    nodata_policy: str,
    aggregation: str,
    normalization_scale_m: float | None = None,
    categories: dict[str, int] | None = None,
) -> FeatureMapReport:
    finite = np.isfinite(values)
    valid_count = int(finite.sum())
    if categories is None:
        summary: NumericFeatureSummary | CategoricalFeatureSummary = _numeric_summary(values, bins)
    else:
        summary = CategoricalFeatureSummary(
            valid_sample_count=valid_count,
            category_counts={
                label: int(np.count_nonzero(values[finite] == code))
                for code, label in sorted(_LANDFORM_NAMES.items())
            },
        )
    return FeatureMapReport(
        name=name,
        algorithm=algorithm,
        units=units,
        raster_file=output_path.name,
        raster_sha256=sha256_file(output_path),
        valid_sample_count=valid_count,
        input_valid_sample_count=input_valid_count,
        coverage_of_input_valid=(valid_count / input_valid_count if input_valid_count else 0.0),
        coverage_of_raster=valid_count / raster_cell_count,
        window_cells=window,
        window_support_m=window_support_m,
        edge_policy=edge_policy,
        nodata_policy=nodata_policy,
        aggregation=aggregation,
        normalization_scale_m=normalization_scale_m,
        summary=summary,
        categories=categories,
    )


def analyze_terrain_raster(
    raster_path: Path,
    output_dir: Path,
    config: TerrainAnalyticsConfig | None = None,
) -> TerrainAnalyticsResult:
    """Create six terrain feature products from one projected ScaleBridge raster."""
    settings = config or TerrainAnalyticsConfig()
    source_path = Path(raster_path)
    if not source_path.is_file():
        raise InvalidRasterError("Terrain-analysis input raster is unavailable")
    source_checksum = sha256_file(source_path)
    try:
        with rasterio.open(source_path) as source:
            if source.count != 1 or source.width < 3 or source.height < 3:
                raise InvalidRasterError("Terrain analysis requires one band of at least 3x3 cells")
            if source.crs is None:
                raise InvalidRasterError("Terrain analysis requires a declared CRS")
            crs = pyproj.CRS.from_wkt(source.crs.to_wkt())
            if not crs.is_projected:
                raise InvalidRasterError("Terrain derivatives require a projected metric CRS")
            if abs(source.transform.b) > 1e-12 or abs(source.transform.d) > 1e-12:
                raise InvalidRasterError("Rotated rasters are not supported by this terrain engine")
            tags = source.tags()
            source_id = tags.get("dataset_id", "")
            parent_checksum = tags.get("source_sha256", "")
            body = tags.get("target_body", "")
            product = tags.get("product", "")
            source_surface_type = tags.get("source_surface_type", "unknown")
            vertical_units = tags.get("output_vertical_units", "")
            effective_resolution_text = tags.get("source_effective_resolution_m")
            if (
                len(source_id) != 64
                or any(char not in "0123456789abcdef" for char in source_id)
                or len(parent_checksum) != 64
                or any(char not in "0123456789abcdef" for char in parent_checksum)
            ):
                raise InvalidRasterError("ScaleBridge source and parent checksums are required")
            if body not in {"mars", "moon", "earth"}:
                raise InvalidRasterError("ScaleBridge target-body metadata is missing or invalid")
            z_factor = _linear_unit_factor(vertical_units, "vertical")
            try:
                effective_resolution_m = (
                    float(effective_resolution_text)
                    if effective_resolution_text is not None
                    else None
                )
            except ValueError as exc:
                raise InvalidRasterError(
                    "Source effective resolution metadata must be numeric"
                ) from exc
            if effective_resolution_m is not None and (
                not math.isfinite(effective_resolution_m) or effective_resolution_m <= 0
            ):
                raise InvalidRasterError(
                    "Source effective resolution metadata must be positive and finite"
                )
            horizontal_factors = [axis.unit_conversion_factor for axis in crs.axis_info[:2]]
            if len(horizontal_factors) != 2 or not all(
                math.isfinite(float(factor)) and float(factor) > 0 for factor in horizontal_factors
            ):
                raise InvalidRasterError("Projected CRS horizontal units are unavailable")
            if not math.isclose(
                float(horizontal_factors[0]), float(horizontal_factors[1]), rel_tol=1e-12
            ):
                raise InvalidRasterError("Projected CRS axes use incompatible horizontal units")
            horizontal_factor = float(horizontal_factors[0])
            dx = abs(source.transform.a) * horizontal_factor
            dy = abs(source.transform.e) * horizontal_factor
            if dx <= 0 or dy <= 0:
                raise InvalidRasterError("Raster pixel dimensions must be positive")
            elevation = source.read(1).astype("float64") * z_factor
            valid = (source.read_masks(1) > 0) & np.isfinite(elevation)
            profile = source.profile.copy()
            width, height = source.width, source.height
            source_crs = crs.to_wkt()
    except InvalidRasterError:
        raise
    except (OSError, rasterio.errors.RasterioError, ValueError) as exc:
        raise InvalidRasterError("Terrain-analysis raster could not be read or validated") from exc

    raster_cells = width * height
    if raster_cells > MAX_ANALYTICS_CELLS:
        raise InvalidRasterError(
            "Terrain analysis is limited to four million in-memory raster cells"
        )
    input_valid_count = int(valid.sum())
    if input_valid_count == 0:
        raise InvalidRasterError("Terrain-analysis raster has no valid elevations")
    neighborhood = _window_size(settings.neighborhood_radius_m, dx, dy)
    support_m = (neighborhood[1] * dx, neighborhood[0] * dy)
    focal_nodata = (
        "Output requires a valid center and at least the configured fraction of cells in the "
        "full rectangular neighborhood; NoData and beyond-raster cells count as missing."
    )
    strict_nodata = (
        "Output is NoData unless the center and all nine cells in the 3x3 stencil are valid."
    )
    features: dict[str, np.ndarray] = {
        "slope": _horn_slope(elevation, valid, dx, dy),
    }
    relief, roughness, tpi = _focal_features(
        elevation, valid, neighborhood, settings.minimum_neighborhood_valid_fraction
    )
    features["local_relief"] = relief
    features["terrain_roughness"] = roughness
    profile_curvature, plan_curvature = _curvatures(elevation, valid, dx, dy)
    features["profile_curvature"] = profile_curvature
    features["plan_curvature"] = plan_curvature
    features["topographic_position_index"] = tpi

    landform_scale_m = settings.landform_standardization_scale_m
    if not settings.landform_morphology_enabled:
        landform_scale_m = None
        landform = np.full(tpi.shape, np.nan, dtype="float64")
    elif landform_scale_m is None:
        valid_tpi = tpi[np.isfinite(tpi)]
        estimated_scale = float(np.std(valid_tpi, ddof=0)) if valid_tpi.size else 0.0
        # A zero or undefined reference scale cannot define comparable classes.
        landform_scale_m = (
            estimated_scale if math.isfinite(estimated_scale) and estimated_scale > 0 else None
        )
        landform = (
            classify_relative_landform(tpi, landform_scale_m)
            if landform_scale_m is not None
            else np.full(tpi.shape, np.nan, dtype="float64")
        )
    else:
        landform = classify_relative_landform(tpi, landform_scale_m)
    features["landform_morphology"] = landform

    output_root = Path(output_dir)
    config_payload = {
        "source_raster_sha256": source_checksum,
        "source_dataset_id": source_id,
        "parent_source_sha256": parent_checksum,
        "target_body": body,
        "crs": source_crs,
        "pixel_width_m": dx,
        "pixel_height_m": dy,
        "source_effective_resolution_m": effective_resolution_m,
        "vertical_units": vertical_units,
        "config": settings.model_dump(mode="json"),
        "algorithms": {
            "slope": "Horn 3x3 weighted finite difference",
            "local_relief": "focal maximum minus focal minimum",
            "terrain_roughness": "population standard deviation of elevations in a focal window",
            "profile_curvature": "directional second-derivative curvature, convex negative",
            "plan_curvature": "cross-slope second-derivative curvature, convex positive",
            "topographic_position_index": "center elevation minus focal arithmetic mean",
            "landform_morphology": "single-scale standardized TPI classes",
        },
        "software": {"numpy": np.__version__, "scipy": scipy.__version__},
    }
    digest = hashlib.sha256(
        json.dumps(config_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    run_id = digest[:20]
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    definitions: dict[str, FeatureDefinition] = {
        "slope": (
            "Horn 3x3 weighted finite-difference gradient; arctangent of gradient magnitude",
            "degree",
            "3x3 Horn stencil",
            (3, 3),
            (3 * dx, 3 * dy),
            "Outermost row/column is NoData because the full 3x3 stencil is unavailable.",
            strict_nodata,
            "Pointwise gradient; degrees from the metric rise/run magnitude.",
        ),
        "local_relief": (
            "Local relief = maximum elevation - minimum elevation",
            "m",
            f"rectangular focal window {neighborhood[1]} columns x {neighborhood[0]} rows",
            neighborhood,
            support_m,
            (
                "Window is centered; beyond-raster cells count as missing; "
                "insufficient windows are NoData."
            ),
            focal_nodata,
            "Maximum minus minimum of available neighborhood elevations.",
        ),
        "terrain_roughness": (
            "Elevation standard deviation (population, ddof=0); not vector ruggedness",
            "m",
            f"rectangular focal window {neighborhood[1]} columns x {neighborhood[0]} rows",
            neighborhood,
            support_m,
            (
                "Window is centered; beyond-raster cells count as missing; "
                "insufficient windows are NoData."
            ),
            focal_nodata,
            "Population standard deviation of available neighborhood elevations.",
        ),
        "profile_curvature": (
            "Directional second derivative along the steepest-slope direction; convex negative",
            "m^-1",
            "3x3 centered second-derivative stencil",
            (3, 3),
            (3 * dx, 3 * dy),
            "Outermost row/column is NoData; zero-gradient non-flat critical points are undefined.",
            strict_nodata + " Non-flat zero-gradient points are NoData.",
            "Derivative curvature in the steepest-slope direction.",
        ),
        "plan_curvature": (
            "Directional second derivative across the steepest-slope direction; convex positive",
            "m^-1",
            "3x3 centered second-derivative stencil",
            (3, 3),
            (3 * dx, 3 * dy),
            "Outermost row/column is NoData; zero-gradient non-flat critical points are undefined.",
            strict_nodata + " Non-flat zero-gradient points are NoData.",
            ("Derivative curvature perpendicular to steepest slope; convex is positive."),
        ),
        "topographic_position_index": (
            "Center elevation minus arithmetic mean of the focal neighborhood, including center",
            "m",
            f"rectangular focal window {neighborhood[1]} columns x {neighborhood[0]} rows",
            neighborhood,
            support_m,
            (
                "Window is centered; beyond-raster cells count as missing; "
                "insufficient windows are NoData."
            ),
            focal_nodata,
            (
                "Positive is locally high, negative locally low, relative to the "
                "selected neighborhood."
            ),
        ),
        "landform_morphology": (
            "Single-scale relative-position classes from TPI divided by the shared reference "
            "TPI population standard deviation; unavailable when no positive scale exists",
            "class code",
            (
                f"TPI window {neighborhood[1]} columns x {neighborhood[0]} rows; "
                + (
                    f"shared TPI standardization scale {landform_scale_m:.12g} m"
                    if landform_scale_m is not None
                    else "shared TPI standardization scale unavailable"
                )
            ),
            neighborhood,
            support_m,
            "Inherits TPI edges and NoData; classes describe relative position only.",
            focal_nodata,
            "-1=relative low; 0=near local mean; 1=relative high; not geology or material.",
        ),
    }
    feature_reports: dict[str, FeatureMapReport] = {}
    feature_paths: dict[str, str] = {}
    for name, values in features.items():
        definition = definitions[name]
        file_name = f"{name}.tif"
        feature_path = run_dir / file_name
        tags = {
            "source_dataset_id": source_id,
            "source_raster_sha256": source_checksum,
            "parent_source_sha256": parent_checksum,
            "target_body": body,
            "feature": name,
            "algorithm": definition[0],
            "units": definition[1],
            "horizontal_pixel_width_m": f"{dx:.12g}",
            "horizontal_pixel_height_m": f"{dy:.12g}",
            "neighborhood_cells": str(definition[3]),
            "neighborhood_support_m": str(definition[4]),
            "edge_policy": definition[5],
            "nodata_policy": definition[6],
            "aggregation": definition[7],
            "terratwin_reproducibility_sha256": digest,
        }
        if name == "landform_morphology":
            tags["normalization_scale_status"] = (
                "available" if landform_scale_m is not None else "unavailable"
            )
            if landform_scale_m is not None:
                tags["normalization_scale_m"] = f"{landform_scale_m:.12g}"
            encoded = np.where(np.isfinite(values), values, -32768).astype("int16")
            out_profile = {
                **profile,
                "driver": "GTiff",
                "dtype": "int16",
                "count": 1,
                "nodata": -32768,
                "compress": "deflate",
            }
            out_profile.pop("blockxsize", None)
            out_profile.pop("blockysize", None)
            with rasterio.open(feature_path, "w", **out_profile) as output:
                output.write(encoded, 1)
                output.update_tags(
                    **tags,
                    category_codes="-1=relative_low,0=near_local_mean,1=relative_high",
                )
        else:
            _write_feature(feature_path, values, source_profile=profile, tags=tags)
        categories = (
            {label: code for code, label in _LANDFORM_NAMES.items()}
            if name == "landform_morphology"
            else None
        )
        feature_reports[name] = _feature_report(
            name,
            definition[0],
            definition[1],
            values,
            feature_path,
            input_valid_count,
            raster_cells,
            settings.histogram_bins,
            window=definition[3],
            window_support_m=definition[4],
            edge_policy=definition[5],
            nodata_policy=definition[6],
            aggregation=definition[7],
            normalization_scale_m=(landform_scale_m if name == "landform_morphology" else None),
            categories=categories,
        )
        feature_paths[name] = str(feature_path)

    warnings = [
        (
            "Morphometric outputs describe the harmonized raster scale; they do not restore "
            "terrain detail removed by ScaleBridge aggregation."
        ),
        (
            "Single-scale TPI classes describe relative topographic position, not geology, "
            "material, soil, or formal landform taxonomy."
        ),
        (
            "Terrain at or below source effective resolution is not independently resolved "
            "by these derivatives."
        ),
    ]
    if input_valid_count / raster_cells < 0.5:
        warnings.append(
            f"Only {input_valid_count} of {raster_cells} input cells are valid "
            f"({100 * input_valid_count / raster_cells:.2f}%); terrain summaries may not "
            "represent the full requested support."
        )
    if effective_resolution_m is None:
        warnings.append(
            "Source effective spatial resolution is unavailable; output derivatives describe "
            "the harmonized grid posting and do not establish finer terrain detail."
        )
    small_profiles = [
        f"{name} ({item.valid_sample_count})"
        for name, item in feature_reports.items()
        if 0 < item.valid_sample_count < MIN_PROFILE_SAMPLES_FOR_WARNING
    ]
    if small_profiles:
        warnings.append(
            "Very small feature sample counts (<20 cells) are descriptive only and do not "
            "support representative distribution claims: " + ", ".join(small_profiles) + "."
        )
    empty_features = [
        name for name, item in feature_reports.items() if item.valid_sample_count == 0
    ]
    if empty_features:
        warnings.append(
            "No valid cells were produced for: "
            + ", ".join(empty_features)
            + "; input support or resolution is insufficient under configured masks."
        )
    if landform_scale_m is None:
        warnings.append(
            "Landform morphology is unavailable because this surface's TPI contains no valid "
            "samples or has no positive population standard deviation; no class threshold "
            "was invented."
        )
    report = TerrainAnalyticsReport(
        run_id=run_id,
        reproducibility_sha256=digest,
        source_dataset_id=source_id,
        source_raster_sha256=source_checksum,
        target_body=cast(Literal["mars", "moon", "earth"], body),
        source_product=product,
        source_surface_type=source_surface_type,
        crs=source_crs,
        horizontal_units="m",
        vertical_units="m",
        width=width,
        height=height,
        pixel_width_m=dx,
        pixel_height_m=dy,
        source_effective_resolution_m=effective_resolution_m,
        raster_cell_count=raster_cells,
        input_valid_cell_count=input_valid_count,
        input_valid_fraction=input_valid_count / raster_cells,
        config=settings,
        features=feature_reports,
        processing_software={
            "terratwin_terrain_analytics": "0.1.0",
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "rasterio": rasterio.__version__,
            "gdal": rasterio.__gdal_version__,
            "pyproj": pyproj.__version__,
        },
        warnings=warnings,
    )
    report_path = run_dir / "report.json"
    report_path.write_text(report.model_dump_json(indent=2))
    feature_paths["report"] = str(report_path)
    return TerrainAnalyticsResult(report=report, feature_paths=feature_paths)
