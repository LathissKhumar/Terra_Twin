"""Deterministic, coverage-gated Earth terrain-window comparison."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pyproj
import rasterio
import scipy
from pyproj import Transformer
from rasterio.windows import Window
from rasterio.windows import bounds as window_bounds
from scipy.stats import wasserstein_distance

from app.domain.schemas.analogue_discovery import (
    ROVER_MOBILITY_PROFILE,
    CandidateResult,
    CandidateStatus,
    CandidateWindow,
    DiscoveryConfig,
    DiscoveryReport,
    FeatureComparison,
    FeatureName,
    MissionExperimentProfile,
    PlanetaryReferenceWindow,
)
from app.engines.data_ingestion.ingestion import sha256_file

DISCOVERY_ENGINE_VERSION = "0.7.0"
MAX_BOOTSTRAP_FEATURE_SAMPLES = 1_000_000_000
_CONTINUOUS_UNITS: dict[str, str] = {
    "slope": "degree",
    "local_relief": "m",
    "terrain_roughness": "m",
    "profile_curvature": "m^-1",
    "plan_curvature": "m^-1",
    "topographic_position_index": "m",
}
_REQUIRED_SCALE_FLOORS: dict[FeatureName, float] = {
    "slope": 1.0,
    "local_relief": 1.0,
    "terrain_roughness": 0.5,
    "profile_curvature": 1e-5,
    "plan_curvature": 1e-5,
    "topographic_position_index": 1.0,
    "landform_morphology": 1.0,
}


def load_mission_profile(path: Path) -> MissionExperimentProfile:
    """Load and validate a researcher-editable, versioned profile JSON file."""
    try:
        return MissionExperimentProfile.model_validate_json(path.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError("Mission experiment profile file is unreadable or invalid") from exc


def _finite_values(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype="float64").ravel()
    return array[np.isfinite(array)]


def _bootstrap_wasserstein_standard_error(
    reference: np.ndarray,
    candidate: np.ndarray,
    *,
    replicates: int,
    random_seed: int,
    normalization_scale: float,
) -> float:
    """Bootstrap exact empirical W1 distances without sorting each resample.

    Multinomial resampling of observed-value frequencies is equivalent to drawing
    observations with replacement. It lets each replicate integrate the empirical
    CDF difference over one fixed, sorted value support.
    """
    support, inverse = np.unique(np.concatenate((reference, candidate)), return_inverse=True)
    reference_frequencies = np.bincount(inverse[: reference.size], minlength=support.size)
    candidate_frequencies = np.bincount(inverse[reference.size :], minlength=support.size)
    rng = np.random.default_rng(random_seed)
    distances = np.empty(replicates, dtype="float64")
    support_gaps = np.diff(support)
    max_batch_cells = 1_000_000
    batch_size = max(1, min(replicates, max_batch_cells // support.size))
    for start in range(0, replicates, batch_size):
        stop = min(replicates, start + batch_size)
        reference_draws = rng.multinomial(
            reference.size,
            reference_frequencies / reference.size,
            size=stop - start,
        )
        candidate_draws = rng.multinomial(
            candidate.size,
            candidate_frequencies / candidate.size,
            size=stop - start,
        )
        cdf_difference = np.cumsum(
            reference_draws / reference.size - candidate_draws / candidate.size,
            axis=1,
            dtype="float64",
        )
        distances[start:stop] = (np.abs(cdf_difference[:, :-1]) * support_gaps[None, :]).sum(
            axis=1
        ) / normalization_scale
    return float(np.std(distances, ddof=1))


def _scale_floor(feature: FeatureName, floors: Mapping[FeatureName, float] | None = None) -> float:
    configured = floors or _REQUIRED_SCALE_FLOORS
    return configured.get(feature, _REQUIRED_SCALE_FLOORS[feature])


def _feature_distance_with_scale(
    feature: FeatureName, reference: np.ndarray, candidate: np.ndarray, scale: float
) -> float:
    if feature == "landform_morphology":
        categories = (-1, 0, 1)
        ref = (
            np.array([np.count_nonzero(reference == code) for code in categories]) / reference.size
        )
        cand = (
            np.array([np.count_nonzero(candidate == code) for code in categories]) / candidate.size
        )
        return float(0.5 * np.abs(ref - cand).sum())
    return float(wasserstein_distance(reference, candidate) / scale)


def _spatial_block_standard_errors(
    reference_maps: dict[str, np.ndarray],
    candidate_maps: dict[str, np.ndarray],
    comparisons: dict[str, FeatureComparison],
    profile: MissionExperimentProfile,
    *,
    replicates: int,
    random_seed: int,
    block_cells: int,
) -> tuple[dict[str, float], float]:
    """Joint moving-block bootstrap over aligned 2D feature maps.

    One spatial block draw is shared by all features on each surface and one
    replicate's score is computed jointly, preserving within-surface spatial
    and cross-feature dependence. Blocks use the configured cell side and a
    deterministic, non-overlapping partition; the result is variability, not
    a calibrated confidence interval.
    """
    if replicates < 2:
        return {}, 0.0
    shapes = {
        np.asarray(values).shape for values in (*reference_maps.values(), *candidate_maps.values())
    }
    if len(shapes) != 1 or len(next(iter(shapes))) != 2:
        raise ValueError("Spatial bootstrap requires aligned 2D feature maps")
    height, width = next(iter(shapes))

    def blocks_for(maps: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        starts = [
            (row, col)
            for row in range(0, height, block_cells)
            for col in range(0, width, block_cells)
        ]
        result: dict[str, np.ndarray] = {}
        for feature in profile.required_features:
            values = np.asarray(maps[feature], dtype="float64")
            blocks = np.full((len(starts), block_cells, block_cells), np.nan)
            for index, (row, col) in enumerate(starts):
                patch = values[row : row + block_cells, col : col + block_cells]
                blocks[index, : patch.shape[0], : patch.shape[1]] = patch
            result[feature] = blocks
        return result

    reference_blocks = blocks_for(reference_maps)
    candidate_blocks = blocks_for(candidate_maps)
    if len(next(iter(reference_blocks.values()))) < 2:
        raise ValueError("Spatial bootstrap requires at least two blocks per surface")
    rng = np.random.default_rng(random_seed)
    weights = profile.feature_weights
    weight_total = sum(weights.values())
    replicate_distances = {feature: np.empty(replicates) for feature in profile.required_features}
    weighted_scores = np.empty(replicates)
    for replicate in range(replicates):
        ref_indices = rng.integers(
            0,
            len(next(iter(reference_blocks.values()))),
            size=len(next(iter(reference_blocks.values()))),
        )
        cand_indices = rng.integers(
            0,
            len(next(iter(candidate_blocks.values()))),
            size=len(next(iter(candidate_blocks.values()))),
        )
        score = 0.0
        for feature in profile.required_features:
            ref_values = _finite_values(reference_blocks[feature][ref_indices])
            cand_values = _finite_values(candidate_blocks[feature][cand_indices])
            if not ref_values.size or not cand_values.size:
                raise ValueError("Spatial bootstrap produced an empty feature sample")
            scale = comparisons[feature].normalization_scale or 1.0
            distance = _feature_distance_with_scale(feature, ref_values, cand_values, scale)
            replicate_distances[feature][replicate] = distance
            score += weights[feature] * distance / weight_total
        weighted_scores[replicate] = score
    return (
        {feature: float(np.std(values, ddof=1)) for feature, values in replicate_distances.items()},
        float(np.std(weighted_scores, ddof=1)),
    )


def _distribution_summary(values: np.ndarray) -> dict[str, float]:
    if values.size == 0:
        return {}
    q05, q25, median, q75, q95 = np.quantile(values, [0.05, 0.25, 0.5, 0.75, 0.95])
    return {
        "mean": float(np.mean(values)),
        "median": float(median),
        "standard_deviation": float(np.std(values, ddof=0)),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
        "percentile_05": float(q05),
        "percentile_25": float(q25),
        "percentile_75": float(q75),
        "percentile_95": float(q95),
    }


def compare_feature_distributions(
    feature: FeatureName,
    reference_values: np.ndarray,
    candidate_values: np.ndarray,
    *,
    reference_coverage: float = 1.0,
    candidate_coverage: float = 1.0,
    bootstrap_replicates: int = 0,
    random_seed: int = 0,
    normalization_scale_floors: Mapping[FeatureName, float] | None = None,
) -> FeatureComparison:
    """Compute a robust-scale-normalized Wasserstein or categorical TV distance."""
    reference = _finite_values(reference_values)
    candidate = _finite_values(candidate_values)
    if not 0 <= reference_coverage <= 1 or not 0 <= candidate_coverage <= 1:
        raise ValueError("Feature coverage must lie in [0, 1]")
    if feature == "landform_morphology":
        method = "total variation distance over relative-position class proportions"
        units = "dimensionless"
        if reference.size == 0 or candidate.size == 0:
            return FeatureComparison(
                feature=feature,
                method=method,
                units=units,
                reference_sample_count=int(reference.size),
                candidate_sample_count=int(candidate.size),
                reference_coverage=reference_coverage,
                candidate_coverage=candidate_coverage,
                reference_class_fractions={},
                candidate_class_fractions={},
            )
        categories = (-1, 0, 1)
        ref_prop = np.array([np.count_nonzero(reference == code) for code in categories]) / len(
            reference
        )
        cand_prop = np.array([np.count_nonzero(candidate == code) for code in categories]) / len(
            candidate
        )
        distance = float(0.5 * np.abs(ref_prop - cand_prop).sum())
        reference_fractions = {
            str(code): float(fraction) for code, fraction in zip(categories, ref_prop, strict=True)
        }
        candidate_fractions = {
            str(code): float(fraction) for code, fraction in zip(categories, cand_prop, strict=True)
        }
        standard_error: float | None = None
        if bootstrap_replicates > 1:
            rng = np.random.default_rng(random_seed)
            samples = np.empty(bootstrap_replicates, dtype="float64")
            for index in range(bootstrap_replicates):
                ref_sample = rng.choice(reference, reference.size, replace=True)
                cand_sample = rng.choice(candidate, candidate.size, replace=True)
                ref_frequency = np.array(
                    [np.count_nonzero(ref_sample == code) for code in categories]
                ) / len(ref_sample)
                cand_frequency = np.array(
                    [np.count_nonzero(cand_sample == code) for code in categories]
                ) / len(cand_sample)
                samples[index] = 0.5 * np.abs(ref_frequency - cand_frequency).sum()
            standard_error = float(np.std(samples, ddof=1))
        return FeatureComparison(
            feature=feature,
            method=method,
            units=units,
            reference_sample_count=int(reference.size),
            candidate_sample_count=int(candidate.size),
            reference_coverage=reference_coverage,
            candidate_coverage=candidate_coverage,
            normalization_scale=1.0,
            normalized_distance=distance,
            distance_standard_error=standard_error,
            reference_class_fractions=reference_fractions,
            candidate_class_fractions=candidate_fractions,
        )

    method = (
        "first Wasserstein distance divided by max(reference IQR, configured feature scale floor)"
    )
    units = _CONTINUOUS_UNITS[feature]
    if reference.size == 0 or candidate.size == 0:
        return FeatureComparison(
            feature=feature,
            method=method,
            units=units,
            reference_sample_count=int(reference.size),
            candidate_sample_count=int(candidate.size),
            reference_coverage=reference_coverage,
            candidate_coverage=candidate_coverage,
        )

    ref_q25, ref_q75 = np.quantile(reference, [0.25, 0.75])
    scale = max(
        float(ref_q75 - ref_q25),
        _scale_floor(feature, normalization_scale_floors),
    )
    raw_distance = float(wasserstein_distance(reference, candidate))
    distance = raw_distance / scale
    ref_median = float(np.median(reference))
    cand_median = float(np.median(candidate))
    standard_error = None
    if bootstrap_replicates > 1:
        standard_error = _bootstrap_wasserstein_standard_error(
            reference,
            candidate,
            replicates=bootstrap_replicates,
            random_seed=random_seed,
            normalization_scale=scale,
        )
    return FeatureComparison(
        feature=feature,
        method=method,
        units=units,
        reference_sample_count=int(reference.size),
        candidate_sample_count=int(candidate.size),
        reference_coverage=reference_coverage,
        candidate_coverage=candidate_coverage,
        wasserstein_distance=raw_distance,
        median_difference=cand_median - ref_median,
        normalization_scale=scale,
        normalized_distance=distance,
        distance_standard_error=standard_error,
        reference_median=ref_median,
        candidate_median=cand_median,
        reference_summary=_distribution_summary(reference),
        candidate_summary=_distribution_summary(candidate),
    )


class _ScoredProfile:
    def __init__(
        self,
        comparisons: dict[str, FeatureComparison],
        status: CandidateStatus,
        weighted_distance: float | None,
        standard_error: float | None,
        missing_features: list[FeatureName],
        coverage: float,
    ) -> None:
        self.comparisons = comparisons
        self.status = status
        self.weighted_distance = weighted_distance
        self.standard_error = standard_error
        self.missing_features = missing_features
        self.coverage = coverage


def score_feature_profiles(
    reference_profiles: dict[str, np.ndarray],
    candidate_profiles: dict[str, np.ndarray],
    reference_feature_coverage: dict[str, float],
    candidate_feature_coverage: dict[str, float],
    mission_profile: MissionExperimentProfile,
    *,
    minimum_coverage: float,
    minimum_samples: int,
    bootstrap_replicates: int,
    random_seed: int,
    normalization_scale_floors: Mapping[FeatureName, float] | None = None,
    spatial_bootstrap_block_cells: int = 3,
) -> _ScoredProfile:
    """Score all required features; incomplete evidence never gets a partial rank."""
    comparisons: dict[str, FeatureComparison] = {}
    missing: list[FeatureName] = []
    coverage_values: list[float] = []
    for feature in mission_profile.required_features:
        reference = _finite_values(reference_profiles.get(feature, np.array([])))
        candidate = _finite_values(candidate_profiles.get(feature, np.array([])))
        reference_coverage = float(reference_feature_coverage.get(feature, 0.0))
        candidate_coverage = float(candidate_feature_coverage.get(feature, 0.0))
        coverage_values.extend((reference_coverage, candidate_coverage))
        comparison = compare_feature_distributions(
            feature,
            reference,
            candidate,
            reference_coverage=reference_coverage,
            candidate_coverage=candidate_coverage,
            bootstrap_replicates=(bootstrap_replicates if reference.ndim == 1 else 0),
            random_seed=random_seed + len(comparisons),
            normalization_scale_floors=normalization_scale_floors,
        )
        comparisons[feature] = comparison
        if (
            reference.size < minimum_samples
            or candidate.size < minimum_samples
            or reference_coverage < minimum_coverage
            or candidate_coverage < minimum_coverage
            or comparison.normalized_distance is None
        ):
            missing.append(feature)

    overall_coverage = min(coverage_values, default=0.0)
    if missing:
        return _ScoredProfile(
            comparisons, "insufficient_evidence", None, None, missing, overall_coverage
        )

    spatial_se: dict[str, float] = {}
    joint_score_se: float | None = None
    if bootstrap_replicates > 1 and all(
        np.asarray(reference_profiles[feature]).ndim == 2
        and np.asarray(candidate_profiles[feature]).ndim == 2
        for feature in mission_profile.required_features
    ):
        spatial_se, joint_score_se = _spatial_block_standard_errors(
            reference_profiles,
            candidate_profiles,
            comparisons,
            mission_profile,
            replicates=bootstrap_replicates,
            random_seed=random_seed,
            block_cells=spatial_bootstrap_block_cells,
        )
        comparisons = {
            feature: item.model_copy(update={"distance_standard_error": spatial_se[feature]})
            for feature, item in comparisons.items()
        }

    weight_sum = sum(mission_profile.feature_weights.values())
    normalized_weights = {
        feature: weight / weight_sum for feature, weight in mission_profile.feature_weights.items()
    }
    score = 0.0
    uncertainty_terms: list[float] = []
    for feature in mission_profile.required_features:
        distance = comparisons[feature].normalized_distance
        if distance is None:
            raise RuntimeError("Evidence gate passed without a valid feature distance")
        score += normalized_weights[feature] * distance
        standard_error = comparisons[feature].distance_standard_error
        if standard_error is not None:
            uncertainty_terms.append((normalized_weights[feature] * standard_error) ** 2)
    score_se = (
        joint_score_se
        if joint_score_se is not None
        else (
            math.sqrt(sum(uncertainty_terms))
            if len(uncertainty_terms) == len(mission_profile.required_features)
            else None
        )
    )
    return _ScoredProfile(comparisons, "eligible", float(score), score_se, [], overall_coverage)


def _axis_positions(
    length: int,
    window: int,
    stride: int,
    minimum_start: int = 0,
    maximum_end: int | None = None,
) -> list[int]:
    end_limit = length if maximum_end is None else min(length, maximum_end)
    if end_limit - minimum_start < window:
        return []
    first = math.ceil(minimum_start / stride) * stride
    last = end_limit - window
    positions = list(range(first, last + 1, stride))
    if not positions:
        positions = [last]
    if positions[-1] != last:
        positions.append(last)
    return positions


def generate_candidate_windows(
    *,
    raster_width: int,
    raster_height: int,
    pixel_width_m: float,
    pixel_height_m: float,
    window_width_m: float,
    window_height_m: float,
    stride_m: float,
    maximum_candidates: int,
    minimum_col: int = 0,
    minimum_row: int = 0,
    maximum_col: int | None = None,
    maximum_row: int | None = None,
) -> list[CandidateWindow]:
    """Create unique full windows; append trailing edge offsets for complete coverage."""
    numeric = (pixel_width_m, pixel_height_m, window_width_m, window_height_m, stride_m)
    if not all(math.isfinite(value) and value > 0 for value in numeric):
        raise ValueError(
            "Grid spacing and physical candidate dimensions must be positive finite values"
        )
    if min(raster_width, raster_height, maximum_candidates) <= 0:
        raise ValueError("Raster shape and maximum candidate count must be positive")
    if (
        minimum_col < 0
        or minimum_row < 0
        or maximum_col is not None
        and not minimum_col < maximum_col <= raster_width
        or maximum_row is not None
        and not minimum_row < maximum_row <= raster_height
    ):
        raise ValueError("Candidate pixel search bounds are invalid for the raster")
    window_width = math.ceil(window_width_m / pixel_width_m)
    window_height = math.ceil(window_height_m / pixel_height_m)
    stride_x = max(1, round(stride_m / pixel_width_m))
    stride_y = max(1, round(stride_m / pixel_height_m))
    columns = _axis_positions(raster_width, window_width, stride_x, minimum_col, maximum_col)
    rows = _axis_positions(raster_height, window_height, stride_y, minimum_row, maximum_row)
    candidate_count = len(columns) * len(rows)
    if candidate_count > maximum_candidates:
        raise ValueError(
            f"Search would generate {candidate_count} windows, exceeding maximum candidate count "
            f"({maximum_candidates}); increase stride or reduce the search boundary"
        )
    return [
        CandidateWindow(
            row_off=row,
            col_off=column,
            height=window_height,
            width=window_width,
            actual_width_m=window_width * pixel_width_m,
            actual_height_m=window_height * pixel_height_m,
        )
        for row in rows
        for column in columns
    ]


def _read_raster(
    path: Path,
) -> tuple[np.ndarray, rasterio.Affine, rasterio.crs.CRS, dict[str, str]]:
    with rasterio.open(path) as dataset:
        if dataset.count != 1 or dataset.crs is None:
            raise ValueError(f"Feature raster must have one band and a CRS: {path.name}")
        if not math.isclose(dataset.transform.b, 0, abs_tol=1e-12) or not math.isclose(
            dataset.transform.d, 0, abs_tol=1e-12
        ):
            raise ValueError("Rotated discovery grids are not supported")
        masked = dataset.read(1, masked=True)
        values = np.asarray(masked.astype("float64").filled(np.nan), dtype="float64")
        return values, dataset.transform, dataset.crs, dataset.tags()


def _require_projected_metric_crs(crs: rasterio.crs.CRS, label: str) -> None:
    projected = pyproj.CRS.from_wkt(crs.to_wkt())
    if not projected.is_projected or len(projected.axis_info) < 2:
        raise ValueError(f"{label} raster must use a projected metric CRS")
    units = [axis.unit_name.casefold() for axis in projected.axis_info[:2]]
    if any(unit not in {"metre", "meter", "metres", "meters"} for unit in units):
        raise ValueError(f"{label} raster horizontal units must be metres")


def _read_feature_directory(
    feature_dir: Path,
    analytics_report_path: Path,
    selected_features: list[FeatureName],
) -> tuple[dict[str, np.ndarray], dict[str, Any], tuple[Any, ...], Any]:
    report = json.loads(analytics_report_path.read_text())
    profiles: dict[str, np.ndarray] = {}
    grid = None
    transform = None
    for feature in selected_features:
        feature_report = report["features"].get(feature)
        if feature_report is None:
            raise ValueError(f"Terrain analytics report is missing feature {feature}")
        path = feature_dir / feature_report["raster_file"]
        if not path.is_file() or sha256_file(path) != feature_report["raster_sha256"]:
            raise ValueError(f"Feature raster missing or checksum mismatch: {feature}")
        array, current_transform, current_crs, tags = _read_raster(path)
        if grid is None:
            grid = (array.shape, current_crs)
            transform = current_transform
        elif grid != (array.shape, current_crs) or transform != current_transform:
            raise ValueError(
                "Terrain feature maps must share identical dimensions, CRS and transform"
            )
        if (
            tags.get("feature") != feature
            or tags.get("source_dataset_id") != report["source_dataset_id"]
            or tags.get("source_raster_sha256") != report["source_raster_sha256"]
        ):
            raise ValueError(f"Feature map provenance tags disagree for {feature}")
        profiles[feature] = array
    if grid is None or transform is None:
        raise ValueError("At least one feature raster is required")
    return profiles, report, grid[0], (transform, grid[1])


def _validate_feature_method_compatibility(
    planetary_report: dict[str, Any], earth_report: dict[str, Any], features: list[FeatureName]
) -> None:
    for feature in features:
        planetary = planetary_report["features"].get(feature)
        earth = earth_report["features"].get(feature)
        if planetary is None or earth is None:
            raise ValueError(f"Both analytics reports must include selected feature {feature}")
        for property_name in (
            "algorithm",
            "units",
            "window_cells",
            "window_support_m",
            "aggregation",
        ):
            if planetary.get(property_name) != earth.get(property_name):
                raise ValueError(
                    f"Selected feature {feature} has incompatible {property_name} metadata"
                )
        if feature == "landform_morphology":
            scale = planetary.get("normalization_scale_m")
            earth_scale = earth.get("normalization_scale_m")
            if scale is None and earth_scale is None:
                planetary_count = planetary.get("valid_sample_count", 0)
                earth_count = earth.get("valid_sample_count", 0)
                if planetary_count == 0 and earth_count == 0:
                    continue
            if scale is None or scale != earth_scale or float(scale) <= 0:
                raise ValueError(
                    "Landform morphology requires the same positive reference TPI scale on "
                    "both surfaces, or must be unavailable with zero samples on both"
                )


def _boundary_for_raster(
    transform: rasterio.Affine,
    width: int,
    height: int,
    crs: rasterio.crs.CRS,
) -> tuple[float, float, float, float]:
    bounds = rasterio.transform.array_bounds(height, width, transform)
    return Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform_bounds(
        bounds[0], bounds[1], bounds[2], bounds[3], densify_pts=41
    )


def _body_geographic_bounds(
    transform: rasterio.Affine,
    width: int,
    height: int,
    crs: rasterio.crs.CRS,
) -> tuple[float, float, float, float]:
    projected_crs = pyproj.CRS.from_wkt(crs.to_wkt())
    body_geodetic = projected_crs.geodetic_crs
    if body_geodetic is None:
        raise ValueError("Planetary terrain CRS does not identify its body's geographic CRS")
    bounds = rasterio.transform.array_bounds(height, width, transform)
    result = Transformer.from_crs(projected_crs, body_geodetic, always_xy=True).transform_bounds(
        bounds[0], bounds[1], bounds[2], bounds[3], densify_pts=41
    )
    if not all(math.isfinite(value) for value in result):
        raise ValueError("Planetary reference boundary transform produced non-finite coordinates")
    return (
        float(result[0]),
        float(result[1]),
        float(result[2]),
        float(result[3]),
    )


def _validate_boundary_within_raster(
    requested: tuple[float, float, float, float],
    raster_boundary: tuple[float, float, float, float],
) -> None:
    tolerance = 1e-8
    if (
        requested[0] < raster_boundary[0] - tolerance
        or requested[1] < raster_boundary[1] - tolerance
        or requested[2] > raster_boundary[2] + tolerance
        or requested[3] > raster_boundary[3] + tolerance
    ):
        raise ValueError("Requested Earth search boundary extends beyond the input raster")


def _geographic_footprint(
    transform: rasterio.Affine,
    candidate: CandidateWindow,
    crs: rasterio.crs.CRS,
) -> tuple[list[tuple[float, float]], tuple[float, float]]:
    left, bottom, right, top = window_bounds(
        Window(candidate.col_off, candidate.row_off, candidate.width, candidate.height), transform
    )
    edge_count = 8
    projected: list[tuple[float, float]] = []
    for start, end in (
        ((left, top), (right, top)),
        ((right, top), (right, bottom)),
        ((right, bottom), (left, bottom)),
        ((left, bottom), (left, top)),
    ):
        projected.extend(
            (
                start[0] + (end[0] - start[0]) * step / edge_count,
                start[1] + (end[1] - start[1]) * step / edge_count,
            )
            for step in range(edge_count)
        )
    projected.append(projected[0])
    to_geo = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    transformed = [to_geo.transform(x, y) for x, y in projected]
    footprint = [(float(point[0]), float(point[1])) for point in transformed]
    centroid_xy = to_geo.transform((left + right) / 2, (bottom + top) / 2)
    centroid = (float(centroid_xy[0]), float(centroid_xy[1]))
    return footprint, centroid


def _inside_boundary(
    footprint: list[tuple[float, float]], boundary: tuple[float, float, float, float]
) -> bool:
    west, south, east, north = boundary
    return all(
        west - 1e-9 <= longitude <= east + 1e-9 and south - 1e-9 <= latitude <= north + 1e-9
        for longitude, latitude in footprint
    )


def _pixel_window_for_geographic_boundary(
    boundary: tuple[float, float, float, float],
    transform: rasterio.Affine,
    width: int,
    height: int,
    crs: rasterio.crs.CRS,
) -> tuple[int, int, int, int]:
    west, south, east, north = Transformer.from_crs(
        "EPSG:4326", crs, always_xy=True
    ).transform_bounds(*boundary, densify_pts=41)
    inverse = ~transform
    pixel_corners = [
        inverse @ (west, south),
        inverse @ (west, north),
        inverse @ (east, south),
        inverse @ (east, north),
    ]
    minimum_col = max(0, math.floor(min(point[0] for point in pixel_corners)))
    minimum_row = max(0, math.floor(min(point[1] for point in pixel_corners)))
    maximum_col = min(width, math.ceil(max(point[0] for point in pixel_corners)))
    maximum_row = min(height, math.ceil(max(point[1] for point in pixel_corners)))
    return minimum_col, minimum_row, maximum_col, maximum_row


def _candidate_id(config_digest: str, row: int, col: int, height: int, width: int) -> str:
    payload = f"{config_digest}:{row}:{col}:{height}:{width}".encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def _window_overlap_iou(a: CandidateWindow, b: CandidateWindow) -> float:
    left = max(a.col_off, b.col_off)
    top = max(a.row_off, b.row_off)
    right = min(a.col_off + a.width, b.col_off + b.width)
    bottom = min(a.row_off + a.height, b.row_off + b.height)
    intersection = max(0, right - left) * max(0, bottom - top)
    union = a.width * a.height + b.width * b.height - intersection
    return intersection / union if union else 0.0


def _cluster_candidates(
    candidates: list[CandidateResult], overlap_threshold: float
) -> list[list[int]]:
    """Greedy nonmaximum suppression groups overlapping windows by priority."""
    if not candidates:
        return []
    priority = sorted(
        range(len(candidates)),
        key=lambda index: (
            candidates[index].weighted_distance is None,
            candidates[index].weighted_distance
            if candidates[index].weighted_distance is not None
            else math.inf,
            candidates[index].candidate_id,
        ),
    )
    priority_position = {candidate_index: order for order, candidate_index in enumerate(priority)}
    bucket_height = max(item.window.height for item in candidates)
    bucket_width = max(item.window.width for item in candidates)
    buckets: dict[tuple[int, int], set[int]] = defaultdict(set)
    candidate_buckets: dict[int, set[tuple[int, int]]] = {}
    for index, item in enumerate(candidates):
        window = item.window
        keys = {
            (row, col)
            for row in range(
                window.row_off // bucket_height,
                (window.row_off + window.height - 1) // bucket_height + 1,
            )
            for col in range(
                window.col_off // bucket_width,
                (window.col_off + window.width - 1) // bucket_width + 1,
            )
        }
        candidate_buckets[index] = keys
        for key in keys:
            buckets[key].add(index)

    remaining = set(range(len(candidates)))
    groups: list[list[int]] = []
    for seed in priority:
        if seed not in remaining:
            continue
        group = [seed]
        remaining.remove(seed)
        nearby: set[int] = set()
        for key in candidate_buckets[seed]:
            nearby.update(buckets[key])
        nearby_in_priority = sorted(nearby, key=priority_position.__getitem__)
        for candidate_index in nearby_in_priority:
            if candidate_index not in remaining or candidate_index not in nearby:
                continue
            if (
                _window_overlap_iou(candidates[seed].window, candidates[candidate_index].window)
                >= overlap_threshold
            ):
                group.append(candidate_index)
                remaining.remove(candidate_index)
        groups.append(group)
    return groups


def cluster_and_rank_candidates(
    candidates: list[CandidateResult], overlap_threshold: float
) -> list[CandidateResult]:
    """Keep one lowest-distance eligible representative per overlap cluster."""
    clusters = _cluster_candidates(candidates, overlap_threshold)
    ranked_representatives: list[int] = []
    output = list(candidates)
    for group in clusters:
        cluster_id = hashlib.sha256(
            ":".join(sorted(output[index].candidate_id for index in group)).encode()
        ).hexdigest()[:16]
        eligible = [index for index in group if output[index].weighted_distance is not None]

        def distance_key(index: int) -> tuple[float, str]:
            distance = output[index].weighted_distance
            if distance is None:
                raise RuntimeError("Candidate ranking encountered a missing weighted distance")
            return distance, output[index].candidate_id

        representative = min(eligible, key=distance_key) if eligible else None
        for index in group:
            output[index] = output[index].model_copy(
                update={
                    "cluster_id": cluster_id,
                    "selected_cluster_representative": index == representative,
                }
            )
        if representative is not None:
            ranked_representatives.append(representative)
    ranked_representatives.sort(key=distance_key)
    for rank, index in enumerate(ranked_representatives, start=1):
        output[index] = output[index].model_copy(update={"ranking": rank})
    return output


def run_discovery(
    *,
    planetary_feature_dir: Path,
    planetary_analytics_report: Path,
    earth_feature_dir: Path,
    earth_analytics_report: Path,
    planetary_relative_dem: Path,
    earth_relative_dem: Path,
    scale_bridge_report_path: Path,
    output_dir: Path,
    config: DiscoveryConfig | None = None,
    mission_profile: MissionExperimentProfile = ROVER_MOBILITY_PROFILE,
    progress_callback: Callable[[int, int], None] | None = None,
) -> DiscoveryReport:
    """Run a local, reproducible Earth-window search against one planetary region."""
    settings = config or DiscoveryConfig()
    if set(mission_profile.required_features) != set(settings.selected_features):
        raise ValueError(
            "Selected features must exactly match the mission profile's weighted required features"
        )
    for path in (
        planetary_relative_dem,
        earth_relative_dem,
        scale_bridge_report_path,
        planetary_analytics_report,
        earth_analytics_report,
    ):
        if not path.is_file():
            raise ValueError(f"Required validated input is unavailable: {path.name}")

    planetary_profiles, planetary_report, planetary_shape, planetary_grid = _read_feature_directory(
        planetary_feature_dir, planetary_analytics_report, settings.selected_features
    )
    earth_profiles, earth_report, earth_shape, earth_grid = _read_feature_directory(
        earth_feature_dir, earth_analytics_report, settings.selected_features
    )
    _validate_feature_method_compatibility(
        planetary_report, earth_report, settings.selected_features
    )
    if planetary_report.get("source_surface_type") != "planetary_dtm":
        raise ValueError("Planetary reference must be a documented terrain DTM surface")
    if earth_report.get("source_surface_type") != "bare_earth_dtm":
        raise ValueError(
            "Rover terrain discovery requires a bare-earth DTM; DSM or unknown surface types "
            "cannot be ranked as terrain analogues"
        )
    earth_transform, earth_crs = earth_grid
    pixel_width_m = abs(float(earth_report["pixel_width_m"]))
    pixel_height_m = abs(float(earth_report["pixel_height_m"]))
    if not math.isclose(
        pixel_width_m, abs(float(planetary_report["pixel_width_m"])), rel_tol=1e-3
    ) or not math.isclose(
        pixel_height_m, abs(float(planetary_report["pixel_height_m"])), rel_tol=1e-3
    ):
        raise ValueError("Planetary and Earth analytics pixel dimensions are incompatible")
    planetary_transform, planetary_crs = planetary_grid
    _require_projected_metric_crs(planetary_crs, "Planetary")
    planetary_pixel_width_m = abs(float(planetary_report["pixel_width_m"]))
    planetary_pixel_height_m = abs(float(planetary_report["pixel_height_m"]))
    if not math.isclose(pixel_width_m, planetary_pixel_width_m, rel_tol=1e-3) or not math.isclose(
        pixel_height_m, planetary_pixel_height_m, rel_tol=1e-3
    ):
        raise ValueError(
            "Planetary and Earth feature grids must have compatible comparison pixel dimensions"
        )
    planetary_window_width = math.ceil(settings.candidate_width_m / planetary_pixel_width_m)
    planetary_window_height = math.ceil(settings.candidate_height_m / planetary_pixel_height_m)
    if planetary_window_width > planetary_shape[1] or planetary_window_height > planetary_shape[0]:
        raise ValueError("Candidate dimensions exceed the selected planetary reference region")
    reference_window_col = (planetary_shape[1] - planetary_window_width) // 2
    reference_window_row = (planetary_shape[0] - planetary_window_height) // 2
    reference_region = np.s_[
        reference_window_row : reference_window_row + planetary_window_height,
        reference_window_col : reference_window_col + planetary_window_width,
    ]
    planetary_profiles = {
        feature: values[reference_region] for feature, values in planetary_profiles.items()
    }
    reference_feature_coverage = {
        feature: float(np.isfinite(values).sum() / values.size)
        for feature, values in planetary_profiles.items()
    }
    reference_window_transform = planetary_transform @ rasterio.Affine.translation(
        reference_window_col, reference_window_row
    )
    planetary_boundary = _body_geographic_bounds(
        reference_window_transform,
        planetary_window_width,
        planetary_window_height,
        planetary_crs,
    )
    planetary_reference_window = PlanetaryReferenceWindow(
        row_off=reference_window_row,
        col_off=reference_window_col,
        height=planetary_window_height,
        width=planetary_window_width,
        center_row=reference_window_row + planetary_window_height / 2,
        center_col=reference_window_col + planetary_window_width / 2,
        requested_width_m=settings.candidate_width_m,
        requested_height_m=settings.candidate_height_m,
        actual_width_m=planetary_window_width * planetary_pixel_width_m,
        actual_height_m=planetary_window_height * planetary_pixel_height_m,
    )
    with rasterio.open(earth_relative_dem) as earth_dem:
        if (
            earth_dem.crs != earth_crs
            or earth_dem.shape != earth_shape
            or earth_dem.transform != earth_transform
        ):
            raise ValueError("Earth DEM and terrain feature rasters are not aligned")
        earth_elevation = earth_dem.read(1, masked=True)
        earth_valid = ~np.ma.getmaskarray(earth_elevation) & np.isfinite(
            np.asarray(earth_elevation.filled(np.nan), dtype="float64")
        )
        earth_width, earth_height = earth_dem.width, earth_dem.height
        if not math.isclose(abs(earth_dem.res[0]), pixel_width_m, rel_tol=1e-9) or not math.isclose(
            abs(earth_dem.res[1]), pixel_height_m, rel_tol=1e-9
        ):
            raise ValueError("Earth DEM pixel spacing differs from its terrain analytics report")
        if earth_dem.crs is None:
            raise ValueError("Earth candidate raster must declare its CRS")
        _require_projected_metric_crs(earth_dem.crs, "Earth candidate")

    scale_report = json.loads(scale_bridge_report_path.read_text())
    if (
        planetary_report["source_raster_sha256"] != scale_report["artifact_sha256"]["planetary"]
        or earth_report["source_raster_sha256"] != scale_report["artifact_sha256"]["earth"]
        or planetary_report["source_dataset_id"] != scale_report["planetary"]["dataset_id"]
        or earth_report["source_dataset_id"] != scale_report["earth"]["dataset_id"]
    ):
        raise ValueError(
            "Terrain analytics reports are not derived from the supplied ScaleBridge run"
        )
    if (
        sha256_file(planetary_relative_dem) != scale_report["artifact_sha256"]["planetary"]
        or sha256_file(earth_relative_dem) != scale_report["artifact_sha256"]["earth"]
    ):
        raise ValueError("ScaleBridge DEM checksum does not match its run report")
    with rasterio.open(planetary_relative_dem) as planetary_dem:
        if (
            planetary_dem.shape != planetary_shape
            or planetary_dem.crs is None
            or planetary_dem.count != 1
            or planetary_dem.crs != planetary_grid[1]
            or planetary_dem.transform != planetary_grid[0]
        ):
            raise ValueError("Planetary DEM and feature rasters are not aligned")

    requested_boundary = settings.search_boundary_wgs84
    search_boundary = requested_boundary or _boundary_for_raster(
        earth_transform, earth_width, earth_height, earth_crs
    )
    if requested_boundary is not None:
        raster_boundary = _boundary_for_raster(
            earth_transform, earth_width, earth_height, earth_crs
        )
        _validate_boundary_within_raster(requested_boundary, raster_boundary)

    minimum_col, minimum_row, maximum_col, maximum_row = _pixel_window_for_geographic_boundary(
        search_boundary, earth_transform, earth_width, earth_height, earth_crs
    )

    windows = generate_candidate_windows(
        raster_width=earth_width,
        raster_height=earth_height,
        pixel_width_m=pixel_width_m,
        pixel_height_m=pixel_height_m,
        window_width_m=settings.candidate_width_m,
        window_height_m=settings.candidate_height_m,
        stride_m=settings.candidate_stride_m,
        maximum_candidates=settings.maximum_candidate_count,
        minimum_col=minimum_col,
        minimum_row=minimum_row,
        maximum_col=maximum_col,
        maximum_row=maximum_row,
    )
    bootstrap_work = (
        len(windows)
        * planetary_window_width
        * planetary_window_height
        * len(settings.selected_features)
        * max(settings.bootstrap_replicates, 1)
    )
    if bootstrap_work > MAX_BOOTSTRAP_FEATURE_SAMPLES:
        raise ValueError(
            "Discovery request exceeds the configured computation budget; reduce candidate "
            "count or window dimensions, or lower bootstrap replicates."
        )
    provenance = {
        "engine_version": DISCOVERY_ENGINE_VERSION,
        "software": {
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "rasterio": rasterio.__version__,
            "gdal": rasterio.__gdal_version__,
            "pyproj": pyproj.__version__,
        },
        "scale_bridge_run_id": scale_report["run_id"],
        "scale_bridge_digest": scale_report["reproducibility_sha256"],
        "planetary_analytics_digest": planetary_report["reproducibility_sha256"],
        "earth_analytics_digest": earth_report["reproducibility_sha256"],
        "mission_profile": mission_profile.model_dump(mode="json"),
        "config": settings.model_dump(mode="json"),
        "search_boundary_wgs84": search_boundary,
    }
    config_digest = hashlib.sha256(
        json.dumps(provenance, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    candidate_results: list[CandidateResult] = []
    callback_interval = max(1, math.ceil(len(windows) / 20))
    for window_index, window in enumerate(windows, start=1):
        if progress_callback is not None and (
            window_index % callback_interval == 0 or window_index == len(windows)
        ):
            progress_callback(window_index, len(windows))
        footprint, centroid = _geographic_footprint(earth_transform, window, earth_crs)
        if not _inside_boundary(footprint, search_boundary):
            continue
        region = np.s_[
            window.row_off : window.row_off + window.height,
            window.col_off : window.col_off + window.width,
        ]
        base_mask = earth_valid[region]
        candidate_profiles = {feature: values[region] for feature, values in earth_profiles.items()}
        feature_coverage: dict[str, float] = {}
        planetary_feature_coverage: dict[str, float] = {}
        earth_feature_coverage: dict[str, float] = {}
        for feature in mission_profile.required_features:
            feature_candidate = candidate_profiles.get(feature, np.array([]))
            reference_coverage = reference_feature_coverage.get(feature, 0.0)
            candidate_feature_coverage = (
                float(np.isfinite(feature_candidate).sum() / feature_candidate.size)
                if feature_candidate.size
                else 0.0
            )
            base_coverage = float(base_mask.sum() / base_mask.size) if base_mask.size else 0.0
            planetary_feature_coverage[feature] = reference_coverage
            earth_feature_coverage[feature] = min(candidate_feature_coverage, base_coverage)
            feature_coverage[feature] = min(reference_coverage, earth_feature_coverage[feature])

        candidate_id = _candidate_id(
            config_digest, window.row_off, window.col_off, window.height, window.width
        )
        scored = score_feature_profiles(
            planetary_profiles,
            candidate_profiles,
            planetary_feature_coverage,
            earth_feature_coverage,
            mission_profile,
            minimum_coverage=settings.minimum_evidence_coverage,
            minimum_samples=settings.minimum_feature_samples,
            bootstrap_replicates=settings.bootstrap_replicates,
            random_seed=int(candidate_id[:8], 16),
            normalization_scale_floors=settings.normalization_scale_floor,
            spatial_bootstrap_block_cells=settings.spatial_bootstrap_block_cells,
        )
        available: list[FeatureName] = [
            comparison.feature
            for comparison in scored.comparisons.values()
            if comparison.normalized_distance is not None
        ]
        comparisons = {
            feature: comparison.model_copy(
                update={
                    "reference_coverage": planetary_feature_coverage.get(feature, 0.0),
                    "candidate_coverage": earth_feature_coverage.get(feature, 0.0),
                }
            )
            for feature, comparison in scored.comparisons.items()
        }
        warnings: list[str] = []
        if scored.missing_features:
            warnings.append("Insufficient required evidence: " + ", ".join(scored.missing_features))
        if planetary_report.get("source_effective_resolution_m") is None:
            warnings.append("Planetary effective spatial resolution is unavailable.")
        if earth_report.get("source_effective_resolution_m") is None:
            warnings.append("Earth effective spatial resolution is unavailable.")
        if not math.isclose(
            window.actual_width_m, planetary_reference_window.actual_width_m, rel_tol=1e-3
        ) or not math.isclose(
            window.actual_height_m, planetary_reference_window.actual_height_m, rel_tol=1e-3
        ):
            raise ValueError(
                "Candidate and planetary comparison windows do not share physical size"
            )
        if base_mask.mean() < settings.minimum_evidence_coverage:
            warnings.append(
                "Earth elevation valid-cell coverage is below the configured threshold."
            )
        candidate_results.append(
            CandidateResult(
                candidate_id=candidate_id,
                window=window,
                geographic_boundary_wgs84=footprint,
                centroid_wgs84=centroid,
                feature_comparisons=comparisons,
                required_features=list(mission_profile.required_features),
                available_features=available,
                missing_features=scored.missing_features,
                feature_coverage=feature_coverage,
                planetary_feature_coverage=planetary_feature_coverage,
                earth_feature_coverage=earth_feature_coverage,
                evidence_coverage=scored.coverage,
                status=scored.status,
                weighted_distance=scored.weighted_distance,
                weighted_distance_standard_error=scored.standard_error,
                cluster_id="",
                selected_cluster_representative=False,
                source_dataset_ids={
                    "planetary": planetary_report["source_dataset_id"],
                    "earth": earth_report["source_dataset_id"],
                },
                source_sha256={
                    "planetary": planetary_report["source_raster_sha256"],
                    "earth": earth_report["source_raster_sha256"],
                },
                processing_configuration_sha256=config_digest,
                mission_profile_id=mission_profile.profile_id,
                mission_profile_version=mission_profile.version,
                scale_bridge_run_id=scale_report["run_id"],
                planetary_analytics_run_id=planetary_report["run_id"],
                earth_analytics_run_id=earth_report["run_id"],
                warnings=warnings,
            )
        )

    candidate_results = cluster_and_rank_candidates(
        candidate_results, settings.duplicate_overlap_iou
    )

    candidate_results.sort(key=lambda item: (item.window.row_off, item.window.col_off))
    run_payload = {
        **provenance,
        "windows": [item.candidate_id for item in candidate_results],
    }
    digest = hashlib.sha256(
        json.dumps(run_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    run_id = digest[:20]
    eligible_count = sum(item.status == "eligible" for item in candidate_results)
    ranked_count = sum(item.ranking is not None for item in candidate_results)
    warnings = [
        "This is a bounded Earth test-window search; it is not a global search or novelty claim.",
        "Lower weighted distance means closer under the configured feature set and weights only.",
        (
            "Provisional mission weights are transparent configuration choices, "
            "not established scientific truths."
        ),
        (
            "Reported standard errors are naive pixel bootstrap variability estimates; "
            "they are not confidence intervals and do not account for spatial autocorrelation, "
            "cross-feature dependence, or source DEM measurement uncertainty."
        ),
    ]
    if planetary_report.get("input_valid_fraction", 0.0) < settings.minimum_evidence_coverage:
        warnings.append(
            "Planetary reference valid-cell coverage is below the configured threshold; candidates "
            "cannot receive a weighted rank unless every required feature meets evidence gates."
        )
    if eligible_count == 0:
        warnings.append("No candidate met all required feature sample-count and coverage gates.")

    report = DiscoveryReport(
        run_id=run_id,
        reproducibility_sha256=digest,
        engine_version=DISCOVERY_ENGINE_VERSION,
        scale_bridge_run_id=scale_report["run_id"],
        mission_profile=mission_profile,
        config=settings,
        search_boundary_wgs84=search_boundary,
        planetary_dataset_id=planetary_report["source_dataset_id"],
        planetary_source_sha256=planetary_report["source_raster_sha256"],
        earth_dataset_id=earth_report["source_dataset_id"],
        earth_source_sha256=earth_report["source_raster_sha256"],
        planetary_analytics_run_id=planetary_report["run_id"],
        earth_analytics_run_id=earth_report["run_id"],
        planetary_effective_resolution_m=planetary_report.get("source_effective_resolution_m"),
        earth_effective_resolution_m=earth_report.get("source_effective_resolution_m"),
        planetary_source_product=planetary_report["source_product"],
        earth_source_product=earth_report["source_product"],
        planetary_surface_type=planetary_report["source_surface_type"],
        earth_surface_type=earth_report["source_surface_type"],
        planetary_reference_boundary_body_lon_lat=planetary_boundary,
        planetary_reference_coordinate_body=planetary_report["target_body"],
        planetary_reference_window=planetary_reference_window,
        uncertainty_method=(
            f"{settings.bootstrap_replicates} deterministic spatial block-bootstrap replicates "
            f"with {settings.spatial_bootstrap_block_cells}x"
            f"{settings.spatial_bootstrap_block_cells}-cell blocks; the same sampled blocks "
            "are used jointly across features and the weighted score, preserving local spatial "
            "and cross-feature dependence within blocks. This is a descriptive resampling "
            "variability estimate, not a calibrated confidence interval. Block size is a "
            "configuration assumption; sensitivity to block size and DEM measurement/instrument "
            "uncertainty are not estimated."
        ),
        earth_pixel_width_m=pixel_width_m,
        earth_pixel_height_m=pixel_height_m,
        planetary_reference_width_m=planetary_reference_window.actual_width_m,
        planetary_reference_height_m=planetary_reference_window.actual_height_m,
        candidate_width_cells=math.ceil(settings.candidate_width_m / pixel_width_m),
        candidate_height_cells=math.ceil(settings.candidate_height_m / pixel_height_m),
        actual_candidate_width_m=math.ceil(settings.candidate_width_m / pixel_width_m)
        * pixel_width_m,
        actual_candidate_height_m=math.ceil(settings.candidate_height_m / pixel_height_m)
        * pixel_height_m,
        actual_stride_x_m=max(1, round(settings.candidate_stride_m / pixel_width_m))
        * pixel_width_m,
        actual_stride_y_m=max(1, round(settings.candidate_stride_m / pixel_height_m))
        * pixel_height_m,
        generated_window_count=len(windows),
        evaluated_window_count=len(candidate_results),
        eligible_candidate_count=eligible_count,
        ranked_candidate_count=ranked_count,
        candidates=candidate_results,
        warnings=warnings,
    )
    output_path = output_dir / run_id / "report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.model_dump_json(indent=2) + "\n")
    return report
