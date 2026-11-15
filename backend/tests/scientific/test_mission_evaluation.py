from __future__ import annotations

from app.domain.schemas.terrain_twin import TerrainTwinMetadata
from app.engines.mission_evaluation.assessment import assess_candidate
from tests.fixtures.assessment_context import (
    PROFILE,
    PROFILE_SHA256,
    TEST_CANDIDATE_ID,
    build_candidate_and_report,
    build_unvalidated_twin,
)


def _assess(candidate, report, twin=None):
    return assess_candidate(
        candidate,
        report,
        PROFILE,
        profile_sha256=PROFILE_SHA256,
        discovery_report_sha256="a" * 64,
        terrain_twin=twin,
    )


def test_insufficient_evidence_withholds_rank_and_weighted_distance() -> None:
    candidate, report = build_candidate_and_report()
    assessment = _assess(candidate, report)

    assert assessment.candidate_id == TEST_CANDIDATE_ID
    assert assessment.overall_evidence_status == "INSUFFICIENT_EVIDENCE"
    assert assessment.weighted_distance is None
    assert assessment.ranking is None
    assert all(
        item.evidence_status == "INSUFFICIENT_EVIDENCE"
        for item in assessment.conclusions
        if item.conclusion_id.startswith("terrain-")
        and item.conclusion_id != "terrain-twin-independent-validation"
    )


def test_sufficient_terrain_evidence_remains_bounded_and_unvalidated() -> None:
    candidate, report = build_candidate_and_report(
        status="eligible", coverage=0.95, sample_count=40
    )
    twin = build_unvalidated_twin()
    assessment = _assess(candidate, report, twin)

    assert assessment.overall_evidence_status == "SUPPORTED_WITH_LIMITS"
    assert assessment.weighted_distance == candidate.weighted_distance
    assert assessment.terrain_twin_validation_status == "unvalidated"
    terrain_findings = [
        item
        for item in assessment.conclusions
        if item.conclusion_id.startswith("terrain-")
        and item.conclusion_id != "terrain-twin-independent-validation"
    ]
    assert len(terrain_findings) == len(PROFILE.required_features)
    assert all(item.evidence_status == "SUPPORTED_WITH_LIMITS" for item in terrain_findings)
    assert all(
        "does not establish rover safety" in item.evidence_interpretation
        for item in terrain_findings
    )


def test_one_low_coverage_feature_is_reported_as_insufficient() -> None:
    candidate, report = build_candidate_and_report(
        status="eligible", coverage=0.95, sample_count=40
    )
    feature = PROFILE.required_features[0]
    comparisons = dict(candidate.feature_comparisons)
    comparisons[feature] = comparisons[feature].model_copy(update={"reference_coverage": 0.1})
    candidate = candidate.model_copy(update={"feature_comparisons": comparisons})

    assessment = _assess(candidate, report)
    findings = {item.conclusion_id: item for item in assessment.conclusions}
    assert findings[f"terrain-{feature}"].evidence_status == "INSUFFICIENT_EVIDENCE"
    assert findings[f"terrain-{feature}"].missing_information
    assert all(
        findings[f"terrain-{other}"].evidence_status == "SUPPORTED_WITH_LIMITS"
        for other in PROFILE.required_features[1:]
    )


def test_conflicting_feature_distances_remain_separate_and_weight_traceable() -> None:
    distances = {feature: 0.15 for feature in PROFILE.required_features}
    distances["slope"] = 0.02
    distances["terrain_roughness"] = 3.4
    candidate, report = build_candidate_and_report(
        status="eligible",
        coverage=0.95,
        sample_count=40,
        normalized_distances=distances,
    )
    configured_distance = sum(
        PROFILE.weights[feature] * distances[feature] for feature in PROFILE.required_features
    ) / sum(PROFILE.weights.values())
    candidate = candidate.model_copy(update={"weighted_distance": configured_distance})

    assessment = _assess(candidate, report)
    measured = {
        finding.conclusion_id.removeprefix("terrain-"): finding.evidence[0].measurement[
            "normalized_distance"
        ]
        for finding in assessment.conclusions
        if finding.conclusion_id.startswith("terrain-")
        and finding.conclusion_id != "terrain-twin-independent-validation"
    }
    assert measured["slope"] == 0.02
    assert measured["terrain_roughness"] == 3.4
    assert assessment.weighted_distance == configured_distance


def test_unknown_soil_and_planetary_environment_are_not_site_measurements() -> None:
    candidate, report = build_candidate_and_report()
    assessment = _assess(candidate, report)
    by_id = {item.conclusion_id: item for item in assessment.conclusions}

    assert by_id["additional-soil_mechanics"].evidence_status == "ADDITIONAL_EVIDENCE_REQUIRED"
    assert by_id["environment-planetary_gravity"].evidence_status == "PROFILE_RULE_ONLY"
    assert (
        by_id["environment-planetary_gravity"].evidence[0].measurement["site_measurement"]
        == "unavailable"
    )
    assert by_id["additional-wheel_traction"].missing_information


def test_missing_twin_is_unavailable_and_wrong_profile_is_rejected() -> None:
    candidate, report = build_candidate_and_report()
    assessment = _assess(candidate, report)
    validation = next(
        item
        for item in assessment.conclusions
        if item.conclusion_id == "terrain-twin-independent-validation"
    )
    assert validation.evidence_status == "UNAVAILABLE"
    assert validation.evidence[0].measurement["validation_metrics_available"] is False

    other_profile = PROFILE.model_copy(update={"profile_id": "OTHER_EXPERIMENT"})
    try:
        assess_candidate(
            candidate,
            report,
            other_profile,
            profile_sha256=PROFILE_SHA256,
            discovery_report_sha256="a" * 64,
            terrain_twin=None,
        )
    except ValueError as error:
        assert "does not match" in str(error)
    else:
        raise AssertionError("Unsupported experiment profile must be rejected")


def test_eligible_claim_does_not_upgrade_unvalidated_twin() -> None:
    candidate, report = build_candidate_and_report(
        status="eligible", coverage=0.95, sample_count=40
    )
    twin = TerrainTwinMetadata.model_construct(
        **{
            **build_unvalidated_twin().__dict__,
            "validation_status": "unvalidated",
        }
    )
    assessment = _assess(candidate, report, twin)
    assert assessment.terrain_twin_validation_status == "unvalidated"
    assert assessment.weighted_distance == 0.3
