"""Evidence-gated rule assessment; this module makes no generative claims."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from app.domain.schemas.analogue_discovery import CandidateResult, DiscoveryReport, FeatureName
from app.domain.schemas.mission_assessment import (
    AssessmentCategory,
    AssessmentConclusion,
    AssessmentEvidenceReference,
    EvidenceStatus,
    MissionAssessment,
    MissionAssessmentProfile,
)
from app.domain.schemas.terrain_twin import TerrainTwinMetadata


def _stable_digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _feature_conclusion(
    feature: FeatureName,
    candidate: CandidateResult,
    report: DiscoveryReport,
    profile: MissionAssessmentProfile,
) -> AssessmentConclusion:
    comparison = candidate.feature_comparisons[feature]
    minimum_coverage = report.config.minimum_evidence_coverage
    minimum_samples = report.config.minimum_feature_samples
    sufficient = (
        candidate.status == "eligible"
        and feature not in candidate.missing_features
        and comparison.reference_sample_count >= minimum_samples
        and comparison.candidate_sample_count >= minimum_samples
        and comparison.reference_coverage >= minimum_coverage
        and comparison.candidate_coverage >= minimum_coverage
        and comparison.normalized_distance is not None
    )
    if sufficient:
        status: EvidenceStatus = "SUPPORTED_WITH_LIMITS"
        interpretation = (
            "The stored feature comparison passes this discovery run's coverage and sample gates. "
            "It is evidence for designing a bounded terrain test only; it does not establish rover "
            "safety, mobility performance, or general planetary equivalence."
        )
    else:
        status = "INSUFFICIENT_EVIDENCE"
        interpretation = (
            "Pipeline measurements exist, but the comparison does not pass the discovery run's "
            "required evidence gates. Do not interpret its distribution distance as a supported "
            "similarity finding."
        )

    measurement: dict[str, float | int | str | None] = {
        "reference_median": comparison.reference_median,
        "candidate_median": comparison.candidate_median,
        "median_difference": comparison.median_difference,
        "normalized_distance": comparison.normalized_distance,
        "distance_standard_error": comparison.distance_standard_error,
        "reference_sample_count": comparison.reference_sample_count,
        "candidate_sample_count": comparison.candidate_sample_count,
        "reference_coverage": comparison.reference_coverage,
        "candidate_coverage": comparison.candidate_coverage,
        "minimum_coverage": minimum_coverage,
        "minimum_samples_per_surface": minimum_samples,
    }
    return AssessmentConclusion(
        conclusion_id=f"terrain-{feature}",
        category="POTENTIALLY_TRANSFERABLE",
        conclusion=(
            f"{feature.replace('_', ' ').capitalize()} is within the profile's terrain-geometry "
            "test domain; no claim of demonstrated transfer is made."
        ),
        evidence_status=status,
        evidence_interpretation=interpretation,
        evidence=[
            AssessmentEvidenceReference(
                source_type="discovery_feature",
                source_record_id=report.run_id,
                source_dataset_id=report.planetary_dataset_id,
                feature=feature,
                source_field=f"candidates[{candidate.candidate_id}].feature_comparisons.{feature}",
                comparison_method=comparison.method,
                measurement=measurement,
            ),
            AssessmentEvidenceReference(
                source_type="discovery_feature",
                source_record_id=report.run_id,
                source_dataset_id=report.earth_dataset_id,
                feature=feature,
                source_field=f"candidates[{candidate.candidate_id}].feature_comparisons.{feature}",
                comparison_method=comparison.method,
                measurement=measurement,
            ),
        ],
        missing_information=(
            []
            if sufficient
            else [
                f"reference samples: {comparison.reference_sample_count} of "
                f"{minimum_samples} required",
                f"candidate samples: {comparison.candidate_sample_count} of "
                f"{minimum_samples} required",
                f"reference coverage: {comparison.reference_coverage:.6f} of "
                f"{minimum_coverage:.6f} required",
                f"candidate coverage: {comparison.candidate_coverage:.6f} of "
                f"{minimum_coverage:.6f} required",
            ]
        ),
        limitations=[
            profile.weight_justifications[feature],
            "Feature-distance uncertainty estimates finite-sample variability only; "
            "it is not DEM measurement uncertainty.",
        ],
    )


def _profile_rule_conclusion(
    *,
    conclusion_id: str,
    category: AssessmentCategory,
    concept: str,
    profile: MissionAssessmentProfile,
    evidence_status: EvidenceStatus,
    interpretation: str,
) -> AssessmentConclusion:
    return AssessmentConclusion(
        conclusion_id=conclusion_id,
        category=category,
        conclusion=concept,
        evidence_status=evidence_status,
        evidence_interpretation=interpretation,
        evidence=[
            AssessmentEvidenceReference(
                source_type="profile_rule",
                source_record_id=f"{profile.profile_id}:{profile.version}",
                source_field=conclusion_id,
                comparison_method="versioned deterministic mission-profile rule",
                measurement={"site_measurement": "unavailable"},
            )
        ],
        missing_information=["No corresponding in-situ or environmental observation is recorded."],
        limitations=["This is an evidence-scope rule, not a measurement from the Earth candidate."],
    )


def assess_candidate(
    candidate: CandidateResult,
    report: DiscoveryReport,
    profile: MissionAssessmentProfile,
    *,
    profile_sha256: str,
    discovery_report_sha256: str,
    terrain_twin: TerrainTwinMetadata | None,
) -> MissionAssessment:
    """Build an explainable finding record from existing, validated run outputs."""
    if profile.profile_id != report.mission_profile.profile_id:
        raise ValueError("Mission profile does not match the candidate discovery profile")
    if profile.version != report.mission_profile.version:
        raise ValueError("Mission profile version does not match the candidate discovery profile")
    if candidate.candidate_id not in {item.candidate_id for item in report.candidates}:
        raise ValueError("Candidate is not present in the supplied discovery report")

    conclusions = [
        _feature_conclusion(feature, candidate, report, profile)
        for feature in profile.required_features
    ]
    for evidence_name in profile.additional_evidence_required:
        conclusions.append(
            _profile_rule_conclusion(
                conclusion_id=f"additional-{evidence_name}",
                category="REQUIRES_ADDITIONAL_EVIDENCE",
                concept=(
                    f"{evidence_name.replace('_', ' ').capitalize()} is not assessed from "
                    "these DEM-derived terrain records."
                ),
                profile=profile,
                evidence_status="ADDITIONAL_EVIDENCE_REQUIRED",
                interpretation=(
                    "No corresponding measurement was found in the source evidence records."
                ),
            )
        )
    for condition in profile.not_reproducible_by_earth_site_alone:
        conclusions.append(
            _profile_rule_conclusion(
                conclusion_id=f"environment-{condition}",
                category="CANNOT_BE_REPRODUCED_BY_THE_EARTH_SITE_ALONE",
                concept=(
                    f"{condition.replace('_', ' ').capitalize()} is outside what an Earth "
                    "terrain site alone can reproduce."
                ),
                profile=profile,
                evidence_status="PROFILE_RULE_ONLY",
                interpretation=(
                    "This conclusion follows the mission-profile scope rule and is not a "
                    "measured candidate property."
                ),
            )
        )

    has_validation_metrics = (
        terrain_twin is not None
        and terrain_twin.validation_status == "validated"
        and terrain_twin.validation_metrics is not None
    )
    validation_status: Literal["validated", "unvalidated", "unavailable"] = (
        "validated"
        if has_validation_metrics
        else "unvalidated"
        if terrain_twin is not None
        else "unavailable"
    )
    validation_evidence_status: EvidenceStatus = (
        "SUPPORTED_WITH_LIMITS"
        if has_validation_metrics
        else "UNVALIDATED"
        if terrain_twin is not None
        else "UNAVAILABLE"
    )
    validation_measurement: dict[str, bool | float | int | str | None] = {
        "validation_status": validation_status,
        "validation_metrics_available": has_validation_metrics,
    }
    if has_validation_metrics and terrain_twin is not None:
        metrics = terrain_twin.validation_metrics
        assert metrics is not None
        validation_measurement.update(
            {
                "mean_absolute_error_m": metrics.mean_absolute_error_m,
                "root_mean_square_error_m": metrics.root_mean_square_error_m,
                "median_absolute_error_m": metrics.median_absolute_error_m,
                "mean_bias_m": metrics.mean_bias_m,
                "valid_sample_count": metrics.valid_sample_count,
                "valid_comparison_area_m2": metrics.valid_comparison_area_m2,
                "valid_coverage": metrics.valid_coverage,
                "reference_dataset_id": terrain_twin.reference_dataset_id,
            }
        )
    conclusions.append(
        AssessmentConclusion(
            conclusion_id="terrain-twin-independent-validation",
            category="POTENTIALLY_TRANSFERABLE",
            conclusion=(
                "Independent mesh comparison metrics are recorded; they describe this DEM pair "
                "and do not establish terrain transferability."
                if has_validation_metrics
                else "The reconstructed mesh has no available independent validation metrics."
            ),
            evidence_status=validation_evidence_status,
            evidence_interpretation=(
                "Metrics are reported without a universal pass/fail threshold. Review source "
                "resolution, datum, coverage and uncertainty before interpreting them."
                if has_validation_metrics
                else (
                    terrain_twin.validation_reason
                    if terrain_twin is not None and terrain_twin.validation_reason
                    else (
                        "No Terrain Twin validation record exists for this candidate "
                        "and discovery run."
                    )
                )
            ),
            evidence=[
                AssessmentEvidenceReference(
                    source_type="terrain_twin",
                    source_record_id=(
                        terrain_twin.terrain_twin_id if terrain_twin else candidate.candidate_id
                    ),
                    source_dataset_id=(
                        terrain_twin.reference_dataset_id
                        if has_validation_metrics and terrain_twin
                        else terrain_twin.source_dataset_id
                        if terrain_twin
                        else None
                    ),
                    feature=None,
                    source_field="validation_metrics"
                    if has_validation_metrics
                    else "validation_status",
                    comparison_method="independent-reference DEM comparison",
                    measurement=validation_measurement,
                )
            ],
            missing_information=(
                []
                if has_validation_metrics
                else ["A distinct compatible elevation reference and datum reconciliation."]
            ),
            limitations=[
                (
                    "Reported comparison metrics do not define an acceptance threshold "
                    "or prove analogue suitability."
                )
                if has_validation_metrics
                else "No reconstruction accuracy or geometry validation claim is made."
            ],
        )
    )

    overall_status: EvidenceStatus = (
        "SUPPORTED_WITH_LIMITS" if candidate.status == "eligible" else "INSUFFICIENT_EVIDENCE"
    )
    limitations = list(dict.fromkeys([*profile.known_limitations, *candidate.warnings]))
    missing: list[str] = list(candidate.missing_features)
    missing.extend(
        f"additional evidence: {item.replace('_', ' ')}"
        for item in profile.additional_evidence_required
    )
    if validation_status != "validated":
        missing.append("independent terrain reconstruction validation")
    assessment_id = _stable_digest(
        {
            "candidate_id": candidate.candidate_id,
            "discovery_run_id": report.run_id,
            "profile_sha256": profile_sha256,
            "discovery_report_sha256": discovery_report_sha256,
            "terrain_twin_id": terrain_twin.terrain_twin_id if terrain_twin else None,
        }
    )[:24]
    return MissionAssessment(
        assessment_schema_version="1.0.0",
        assessment_id=assessment_id,
        candidate_id=candidate.candidate_id,
        discovery_run_id=report.run_id,
        discovery_status=candidate.status,
        ranking=candidate.ranking,
        mission_profile_id=profile.profile_id,
        mission_profile_version=profile.version,
        mission_experiment=profile.experiment_name,
        overall_evidence_status=overall_status,
        evidence_coverage=candidate.evidence_coverage,
        minimum_required_coverage=report.config.minimum_evidence_coverage,
        minimum_required_samples=report.config.minimum_feature_samples,
        weighted_distance=candidate.weighted_distance,
        weighted_distance_standard_error=candidate.weighted_distance_standard_error,
        terrain_twin_validation_status=validation_status,
        conclusions=conclusions,
        missing_evidence=list(dict.fromkeys(missing)),
        limitations=limitations,
        assessment_profile_sha256=profile_sha256,
        source_discovery_report_sha256=discovery_report_sha256,
        uncertainty_method=report.uncertainty_method,
    )
