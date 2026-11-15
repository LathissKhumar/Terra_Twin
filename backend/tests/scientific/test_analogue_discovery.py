"""Numerical and spatial checks for analogue discovery behavior."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.domain.schemas.analogue_discovery import (
    CandidateResult,
    CandidateWindow,
    DiscoveryConfig,
    FeatureComparison,
    FeatureName,
    MissionExperimentProfile,
)
from app.domain.schemas.terrain_analytics import TerrainAnalyticsConfig
from app.engines.analogue_discovery.engine import (
    _bootstrap_wasserstein_standard_error,
    _require_projected_metric_crs,
    _validate_boundary_within_raster,
    _validate_feature_method_compatibility,
    cluster_and_rank_candidates,
    compare_feature_distributions,
    generate_candidate_windows,
    load_mission_profile,
    run_discovery,
    score_feature_profiles,
)
from app.engines.data_ingestion.ingestion import sha256_file
from app.engines.terrain_analytics import analyze_terrain_raster


def test_identical_distributions_have_zero_distance() -> None:
    values = np.array([0.0, 1.0, 3.0, 4.0, 10.0])
    comparison = compare_feature_distributions("slope", values, values.copy())
    assert comparison.wasserstein_distance == pytest.approx(0)
    assert comparison.normalized_distance == pytest.approx(0)


def test_shifted_distribution_distance_matches_manual_reference() -> None:
    reference = np.array([0.0, 0.0, 0.0, 0.0])
    candidate = reference + 2.0
    comparison = compare_feature_distributions("slope", reference, candidate)
    assert comparison.wasserstein_distance == pytest.approx(2.0)
    assert comparison.median_difference == pytest.approx(2.0)
    # Both samples have zero IQR; the versioned 1-degree scale floor applies.
    assert comparison.normalization_scale == pytest.approx(1.0)
    assert comparison.normalized_distance == pytest.approx(2.0)


def test_multinomial_bootstrap_standard_error_matches_independent_wasserstein_loop() -> None:
    from scipy.stats import wasserstein_distance

    reference = np.array([0.0, 1.0, 1.0, 3.0, 4.0])
    candidate = np.array([0.0, 2.0, 2.0, 3.0, 5.0])
    replicates, seed, scale = 64, 19, 2.0
    actual = _bootstrap_wasserstein_standard_error(
        reference,
        candidate,
        replicates=replicates,
        random_seed=seed,
        normalization_scale=scale,
    )
    support, inverse = np.unique(np.concatenate((reference, candidate)), return_inverse=True)
    ref_freq = np.bincount(inverse[: reference.size], minlength=support.size) / reference.size
    cand_freq = np.bincount(inverse[reference.size :], minlength=support.size) / candidate.size
    rng = np.random.default_rng(seed)
    ref_draws = rng.multinomial(reference.size, ref_freq, size=replicates)
    cand_draws = rng.multinomial(candidate.size, cand_freq, size=replicates)
    independently_calculated = np.array(
        [
            wasserstein_distance(np.repeat(support, ref_counts), np.repeat(support, cand_counts))
            / scale
            for ref_counts, cand_counts in zip(ref_draws, cand_draws, strict=True)
        ]
    )
    assert actual == pytest.approx(np.std(independently_calculated, ddof=1))


def test_normalization_uses_planetary_reference_spread_not_candidate_spread() -> None:
    comparison = compare_feature_distributions(
        "slope",
        np.zeros(4),
        np.array([-10.0, 10.0, -10.0, 10.0]),
    )
    assert comparison.normalization_scale == pytest.approx(1.0)
    assert comparison.wasserstein_distance == pytest.approx(10.0)
    assert comparison.normalized_distance == pytest.approx(10.0)


def test_feature_scoring_requires_every_profile_feature_and_coverage() -> None:
    profile = MissionExperimentProfile(
        profile_id="test",
        version="1",
        feature_weights={"slope": 0.5, "topographic_position_index": 0.5},
        required_features=["slope", "topographic_position_index"],
        justifications={"slope": "test", "topographic_position_index": "test"},
    )
    identical = np.arange(24, dtype=float)
    complete = score_feature_profiles(
        {"slope": identical, "topographic_position_index": identical},
        {"slope": identical.copy(), "topographic_position_index": identical.copy()},
        {"slope": 1.0, "topographic_position_index": 1.0},
        {"slope": 1.0, "topographic_position_index": 1.0},
        profile,
        minimum_coverage=0.8,
        minimum_samples=20,
        bootstrap_replicates=20,
        random_seed=11,
    )
    assert complete.status == "eligible"
    assert complete.weighted_distance == pytest.approx(0.0)

    missing = score_feature_profiles(
        {"slope": identical, "topographic_position_index": identical},
        {"slope": identical.copy()},
        {"slope": 1.0, "topographic_position_index": 0.0},
        {"slope": 1.0, "topographic_position_index": 0.0},
        profile,
        minimum_coverage=0.8,
        minimum_samples=20,
        bootstrap_replicates=20,
        random_seed=11,
    )
    assert missing.status == "insufficient_evidence"
    assert missing.weighted_distance is None
    assert "topographic_position_index" in missing.missing_features


def test_low_coverage_never_receives_a_weighted_score() -> None:
    values = np.arange(24, dtype=float)
    profile = MissionExperimentProfile(
        profile_id="slope-only",
        version="1",
        feature_weights={"slope": 1.0},
        required_features=["slope"],
        justifications={"slope": "test"},
    )
    result = score_feature_profiles(
        {"slope": values},
        {"slope": values.copy()},
        {"slope": 0.79},
        {"slope": 0.79},
        profile,
        minimum_coverage=0.8,
        minimum_samples=20,
        bootstrap_replicates=20,
        random_seed=1,
    )
    assert result.status == "insufficient_evidence"
    assert result.weighted_distance is None


def test_source_coverages_are_reported_separately_and_either_can_fail_gate() -> None:
    values = np.arange(24, dtype=float)
    profile = MissionExperimentProfile(
        profile_id="slope-only",
        version="1",
        feature_weights={"slope": 1.0},
        required_features=["slope"],
        justifications={"slope": "test"},
    )
    result = score_feature_profiles(
        {"slope": values},
        {"slope": values.copy()},
        {"slope": 0.9},
        {"slope": 0.2},
        profile,
        minimum_coverage=0.8,
        minimum_samples=20,
        bootstrap_replicates=0,
        random_seed=0,
    )
    comparison = result.comparisons["slope"]
    assert comparison.reference_coverage == pytest.approx(0.9)
    assert comparison.candidate_coverage == pytest.approx(0.2)
    assert result.status == "insufficient_evidence"


def test_nodata_samples_count_as_missing_evidence() -> None:
    values = np.arange(30, dtype=float)
    candidate = values.copy()
    candidate[:12] = np.nan
    profile = MissionExperimentProfile(
        profile_id="slope-only",
        version="1",
        feature_weights={"slope": 1.0},
        required_features=["slope"],
        justifications={"slope": "test"},
    )
    result = score_feature_profiles(
        {"slope": values},
        {"slope": candidate},
        {"slope": 1.0},
        {"slope": 1.0},
        profile,
        minimum_coverage=0.8,
        minimum_samples=20,
        bootstrap_replicates=0,
        random_seed=0,
    )
    assert result.comparisons["slope"].candidate_sample_count == 18
    assert result.status == "insufficient_evidence"
    assert result.weighted_distance is None


def test_candidate_windows_cover_grid_without_duplicates_and_respect_cap() -> None:
    windows = generate_candidate_windows(
        raster_width=11,
        raster_height=9,
        pixel_width_m=10,
        pixel_height_m=10,
        window_width_m=40,
        window_height_m=30,
        stride_m=30,
        maximum_candidates=100,
    )
    positions = [(item.col_off, item.row_off) for item in windows]
    assert len(positions) == len(set(positions))
    assert all(item.col_off + item.width <= 11 for item in windows)
    assert all(item.row_off + item.height <= 9 for item in windows)
    assert (7, 6) in positions
    with pytest.raises(ValueError, match="maximum candidate count"):
        generate_candidate_windows(
            raster_width=11,
            raster_height=9,
            pixel_width_m=10,
            pixel_height_m=10,
            window_width_m=20,
            window_height_m=20,
            stride_m=10,
            maximum_candidates=1,
        )


def test_candidate_generation_is_bounded_to_pixel_search_rectangle() -> None:
    windows = generate_candidate_windows(
        raster_width=11,
        raster_height=9,
        pixel_width_m=10,
        pixel_height_m=10,
        window_width_m=20,
        window_height_m=20,
        stride_m=10,
        maximum_candidates=100,
        minimum_col=3,
        minimum_row=2,
        maximum_col=8,
        maximum_row=7,
    )
    assert windows
    assert all(3 <= item.col_off and item.col_off + item.width <= 8 for item in windows)
    assert all(2 <= item.row_off and item.row_off + item.height <= 7 for item in windows)


def test_invalid_search_boundary_and_duplicate_feature_selection_rejected() -> None:
    with pytest.raises(ValueError):
        DiscoveryConfig(
            search_boundary_wgs84=(20, 10, -20, -10),
        )
    with pytest.raises(ValueError):
        DiscoveryConfig(selected_features=["slope", "slope"])
    with pytest.raises(ValueError, match="extends beyond"):
        _validate_boundary_within_raster((0, 0, 2, 2), (0, 0, 1, 1))
    with pytest.raises(ValueError, match="unique"):
        DiscoveryConfig(selected_features=[])


def test_both_comparison_grids_require_projected_metric_crs() -> None:
    with pytest.raises(ValueError, match="projected metric CRS"):
        _require_projected_metric_crs(rasterio.crs.CRS.from_epsg(4326), "Planetary")
    _require_projected_metric_crs(rasterio.crs.CRS.from_epsg(32643), "Earth")


def test_feature_method_incompatibility_is_rejected() -> None:
    feature_report = {
        "algorithm": "method A",
        "units": "degree",
        "window_cells": [3, 3],
        "window_support_m": [30.0, 30.0],
        "aggregation": "pointwise",
    }
    with pytest.raises(ValueError, match="incompatible algorithm"):
        _validate_feature_method_compatibility(
            {"features": {"slope": feature_report}},
            {"features": {"slope": {**feature_report, "algorithm": "method B"}}},
            ["slope"],
        )


def test_landform_class_threshold_must_match_between_reference_and_candidate() -> None:
    feature_report = {
        "algorithm": "relative-position classes",
        "units": "class code",
        "window_cells": [3, 3],
        "window_support_m": [30.0, 30.0],
        "aggregation": "relative position",
        "normalization_scale_m": 2.5,
    }
    _validate_feature_method_compatibility(
        {"features": {"landform_morphology": feature_report}},
        {"features": {"landform_morphology": feature_report}},
        ["landform_morphology"],
    )
    with pytest.raises(ValueError, match="same positive reference TPI scale"):
        _validate_feature_method_compatibility(
            {"features": {"landform_morphology": feature_report}},
            {"features": {"landform_morphology": {**feature_report, "normalization_scale_m": 1.5}}},
            ["landform_morphology"],
        )


def test_landform_can_be_unavailable_on_both_surfaces_only_without_samples() -> None:
    unavailable = {
        "algorithm": "relative-position classes",
        "units": "class code",
        "window_cells": [3, 3],
        "window_support_m": [30.0, 30.0],
        "aggregation": "relative position",
        "normalization_scale_m": None,
        "valid_sample_count": 0,
    }
    _validate_feature_method_compatibility(
        {"features": {"landform_morphology": unavailable}},
        {"features": {"landform_morphology": unavailable}},
        ["landform_morphology"],
    )
    with pytest.raises(ValueError, match="same positive reference TPI scale"):
        _validate_feature_method_compatibility(
            {"features": {"landform_morphology": unavailable}},
            {
                "features": {
                    "landform_morphology": {
                        **unavailable,
                        "valid_sample_count": 10,
                        "normalization_scale_m": 2.5,
                    }
                }
            },
            ["landform_morphology"],
        )


def test_joint_spatial_block_bootstrap_is_reproducible_and_accounts_for_shared_features() -> None:
    profile = MissionExperimentProfile(
        profile_id="joint",
        version="1",
        feature_weights={"slope": 0.5, "local_relief": 0.5},
        required_features=["slope", "local_relief"],
        justifications={"slope": "test", "local_relief": "test"},
    )
    rows, cols = np.mgrid[:18, :18]
    base = (cols // 3).astype(float)
    reference = {"slope": base, "local_relief": 2 * base}
    candidate = {"slope": base + (rows // 3), "local_relief": 2 * base + 2 * (rows // 3)}
    coverage = {"slope": 1.0, "local_relief": 1.0}
    kwargs = dict(
        reference_profiles=reference,
        candidate_profiles=candidate,
        reference_feature_coverage=coverage,
        candidate_feature_coverage=coverage,
        mission_profile=profile,
        minimum_coverage=0.8,
        minimum_samples=20,
        bootstrap_replicates=50,
        random_seed=43,
        spatial_bootstrap_block_cells=3,
    )
    first = score_feature_profiles(**kwargs)
    second = score_feature_profiles(**kwargs)
    assert first.standard_error == pytest.approx(second.standard_error)
    assert first.standard_error is not None
    assert all(
        comparison.distance_standard_error is not None for comparison in first.comparisons.values()
    )


def test_equal_rank_and_weight_changes_are_deterministic() -> None:
    sample = np.zeros(30, dtype=float)
    profile = MissionExperimentProfile(
        profile_id="balanced",
        version="1",
        feature_weights={"slope": 0.5, "local_relief": 0.5},
        required_features=["slope", "local_relief"],
        justifications={"slope": "test", "local_relief": "test"},
    )
    ref = {"slope": sample, "local_relief": sample}
    candidate = {"slope": sample + 1, "local_relief": sample + 5}
    cov = {"slope": 1.0, "local_relief": 1.0}
    scored_a = score_feature_profiles(
        ref,
        candidate,
        cov,
        cov,
        profile,
        minimum_coverage=0.8,
        minimum_samples=20,
        bootstrap_replicates=30,
        random_seed=7,
    )
    weighted_profile = profile.model_copy(
        update={"feature_weights": {"slope": 0.9, "local_relief": 0.1}}
    )
    scored_b = score_feature_profiles(
        ref,
        candidate,
        cov,
        cov,
        weighted_profile,
        minimum_coverage=0.8,
        minimum_samples=20,
        bootstrap_replicates=30,
        random_seed=7,
    )
    assert scored_a.weighted_distance == pytest.approx(3.0)
    assert scored_b.weighted_distance == pytest.approx(1.4)


def _candidate(candidate_id: str, col: int, score: float) -> CandidateResult:
    window = CandidateWindow(
        row_off=0, col_off=col, width=10, height=10, actual_width_m=10, actual_height_m=10
    )
    comparison = FeatureComparison(
        feature="slope",
        method="test",
        units="degree",
        reference_sample_count=20,
        candidate_sample_count=20,
        reference_coverage=1,
        candidate_coverage=1,
        normalized_distance=score,
    )
    return CandidateResult(
        candidate_id=candidate_id,
        window=window,
        geographic_boundary_wgs84=[(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)],
        centroid_wgs84=(0.5, 0.5),
        feature_comparisons={"slope": comparison},
        required_features=["slope"],
        available_features=["slope"],
        missing_features=[],
        feature_coverage={"slope": 1},
        planetary_feature_coverage={"slope": 1},
        earth_feature_coverage={"slope": 1},
        evidence_coverage=1,
        status="eligible",
        weighted_distance=score,
        cluster_id="",
        selected_cluster_representative=False,
        source_dataset_ids={"planetary": "mars", "earth": "earth"},
        source_sha256={"planetary": "a" * 64, "earth": "b" * 64},
        processing_configuration_sha256="c" * 64,
        mission_profile_id="test",
        mission_profile_version="1",
        scale_bridge_run_id="scale-run",
        planetary_analytics_run_id="mars-features",
        earth_analytics_run_id="earth-features",
        warnings=[],
    )


def test_overlapping_windows_cluster_and_equal_scores_rank_stably() -> None:
    results = cluster_and_rank_candidates(
        [
            _candidate("b", 20, 1.0),
            _candidate("a", 0, 1.0),
            _candidate("c", 5, 0.2),
            _candidate("d", 40, 1.0),
        ],
        overlap_threshold=0.2,
    )
    by_id = {candidate.candidate_id: candidate for candidate in results}
    assert by_id["a"].cluster_id == by_id["c"].cluster_id
    assert by_id["c"].selected_cluster_representative
    assert by_id["a"].ranking is None
    assert by_id["b"].ranking == 2
    assert by_id["d"].ranking == 3
    assert by_id["c"].ranking == 1


def test_landform_distribution_uses_total_variation_distance() -> None:
    reference = np.array([-1, -1, 0, 0, 1, 1], dtype=float)
    same = compare_feature_distributions("landform_morphology", reference, reference.copy())
    different = compare_feature_distributions(
        "landform_morphology", reference, np.array([0, 0, 0, 0, 0, 0], dtype=float)
    )
    assert same.normalized_distance == pytest.approx(0)
    assert different.normalized_distance == pytest.approx(2 / 3)
    assert different.reference_class_fractions == {"-1": 1 / 3, "0": 1 / 3, "1": 1 / 3}
    assert different.candidate_class_fractions == {"-1": 0, "0": 1, "1": 0}


def test_mission_profile_requires_complete_weights_and_positive_finite_weights() -> None:
    feature: FeatureName = "slope"
    with pytest.raises(ValueError):
        MissionExperimentProfile(
            profile_id="bad",
            version="1",
            feature_weights={feature: float("nan")},
            required_features=[feature],
            justifications={feature: "bad"},
        )


def test_versioned_rover_profile_json_loads_with_all_justifications() -> None:
    profile_path = (
        Path(__file__).resolve().parents[2]
        / "config"
        / "mission_profiles"
        / "rover_mobility_and_terrain_navigation.v1.json"
    )
    profile = load_mission_profile(profile_path)
    assert profile.profile_id == "ROVER_MOBILITY_AND_TERRAIN_NAVIGATION"
    assert sum(profile.feature_weights.values()) == pytest.approx(1)
    assert set(profile.feature_weights) == set(profile.justifications)


def test_end_to_end_synthetic_search_ranks_and_reproduces(tmp_path: Path) -> None:
    rows, columns = np.mgrid[:31, :31]
    planetary = 0.1 * columns + 0.2 * rows + 0.03 * columns * rows
    earth = 0.1 * columns + 0.2 * rows + 0.05 * np.sin(columns / 3) * np.cos(rows / 4)
    scale_root = tmp_path / "scale"
    scale_root.mkdir()
    datasets: dict[str, dict[str, str]] = {}
    analytics: dict[str, Path] = {}
    for body, values in (("mars", planetary), ("earth", earth)):
        dem = scale_root / f"{body}.tif"
        dataset_id = ("a" if body == "mars" else "b") * 64
        with rasterio.open(
            dem,
            "w",
            driver="GTiff",
            width=31,
            height=31,
            count=1,
            dtype="float32",
            crs="EPSG:32643",
            transform=from_origin(500_000, 2_000_000, 10, 10),
            nodata=-9999.0,
        ) as raster:
            raster.write(values.astype("float32"), 1)
            raster.update_tags(
                dataset_id=dataset_id,
                target_body=body,
                product=f"Synthetic {body} test DEM",
                source_surface_type=("planetary_dtm" if body == "mars" else "bare_earth_dtm"),
                source_sha256="c" * 64,
                output_vertical_units="m",
            )
        body_config = TerrainAnalyticsConfig(neighborhood_radius_m=10)
        if body == "earth":
            mars_report = json.loads((analytics["mars"] / "report.json").read_text())
            shared_scale = mars_report["features"]["topographic_position_index"]["summary"][
                "standard_deviation"
            ]
            body_config = body_config.model_copy(
                update={"landform_standardization_scale_m": shared_scale}
            )
        result = analyze_terrain_raster(
            dem,
            tmp_path / "analytics" / body,
            body_config,
        )
        analytics[body] = Path(result.feature_paths["slope"]).parent
        datasets[body] = {"dataset_id": dataset_id, "checksum": sha256_file(dem)}

    scale_report = {
        "run_id": "synthetic-scale-run",
        "reproducibility_sha256": "d" * 64,
        "artifact_sha256": {
            "planetary": datasets["mars"]["checksum"],
            "earth": datasets["earth"]["checksum"],
        },
        "planetary": {"dataset_id": datasets["mars"]["dataset_id"]},
        "earth": {"dataset_id": datasets["earth"]["dataset_id"]},
    }
    scale_report_path = scale_root / "report.json"
    scale_report_path.write_text(json.dumps(scale_report))
    config = DiscoveryConfig(
        candidate_width_m=120,
        candidate_height_m=120,
        candidate_stride_m=120,
        minimum_evidence_coverage=0.8,
        minimum_feature_samples=4,
        maximum_candidate_count=100,
        bootstrap_replicates=20,
        duplicate_overlap_iou=0.1,
    )
    args = {
        "planetary_feature_dir": analytics["mars"],
        "planetary_analytics_report": analytics["mars"] / "report.json",
        "earth_feature_dir": analytics["earth"],
        "earth_analytics_report": analytics["earth"] / "report.json",
        "planetary_relative_dem": scale_root / "mars.tif",
        "earth_relative_dem": scale_root / "earth.tif",
        "scale_bridge_report_path": scale_report_path,
        "config": config,
    }
    progress: list[tuple[int, int]] = []
    first = run_discovery(
        output_dir=tmp_path / "results-one",
        progress_callback=lambda completed, total: progress.append((completed, total)),
        **args,
    )
    second = run_discovery(output_dir=tmp_path / "results-two", **args)
    assert first.reproducibility_sha256 == second.reproducibility_sha256
    assert first.generated_window_count == 9
    assert progress[-1] == (9, 9)
    assert all(left[0] < right[0] for left, right in zip(progress, progress[1:], strict=False))
    assert first.eligible_candidate_count > 0
    assert first.ranked_candidate_count > 0
    assert [item.candidate_id for item in first.candidates if item.ranking] == [
        item.candidate_id for item in second.candidates if item.ranking
    ]
    ranked = sorted(
        (item for item in first.candidates if item.ranking is not None),
        key=lambda item: item.ranking or 0,
    )
    assert [item.weighted_distance for item in ranked] == sorted(
        item.weighted_distance for item in ranked
    )
    assert all(item.processing_configuration_sha256 for item in first.candidates)
    assert all(item.planetary_analytics_run_id for item in first.candidates)


def test_selected_features_must_match_mission_profile_before_io(tmp_path: Path) -> None:
    config = DiscoveryConfig(selected_features=["slope"])
    profile = MissionExperimentProfile(
        profile_id="full-rover-profile",
        version="1",
        feature_weights={"slope": 0.5, "local_relief": 0.5},
        required_features=["slope", "local_relief"],
        justifications={"slope": "test", "local_relief": "test"},
    )
    with pytest.raises(ValueError, match="exactly match"):
        run_discovery(
            planetary_feature_dir=tmp_path,
            planetary_analytics_report=tmp_path / "missing.json",
            earth_feature_dir=tmp_path,
            earth_analytics_report=tmp_path / "missing.json",
            planetary_relative_dem=tmp_path / "missing.tif",
            earth_relative_dem=tmp_path / "missing.tif",
            scale_bridge_report_path=tmp_path / "missing-scale.json",
            output_dir=tmp_path / "out",
            config=config,
            mission_profile=profile,
        )
