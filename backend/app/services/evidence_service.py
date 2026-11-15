"""Build immutable, provenance-linked evidence passports from real run records."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, cast

from app.domain.schemas.analogue_discovery import FeatureName
from app.domain.schemas.evidence_passport import (
    AnalogueEvidencePassport,
    FeatureAssessmentEvidence,
    PassportCandidate,
    PassportCoverage,
    PassportDatasetSource,
    PassportPlanetaryReference,
    PassportProcessing,
    PassportProvenance,
    PassportScaleBridge,
    PassportUncertainty,
    PassportWeightedDistance,
)
from app.services.assessment_service import (
    CandidateEvidenceContext,
    build_candidate_assessment,
    load_candidate_evidence,
)


def _sha256_json(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _dataset_source(context: CandidateEvidenceContext, key: str) -> PassportDatasetSource:
    manifest = context.manifests[key]
    body = "planetary" if key == "planetary" else "earth"
    return PassportDatasetSource(
        dataset_id=manifest.id,
        target_body=manifest.target_body,
        provider=manifest.provider,
        product=manifest.product,
        version=manifest.version,
        source_url=manifest.source_url,
        downloaded_at=manifest.downloaded_at,
        raw_checksum_sha256=manifest.checksum_sha256,
        manifest_checksum_sha256=context.manifest_sha256[key],
        discovery_processing_checksum_sha256=context.source_processing_sha256[body],
        file_size_bytes=manifest.file_size_bytes,
        crs=manifest.crs,
        bounds=manifest.bounds,
        dimensions=(manifest.width, manifest.height),
        pixel_resolution=(manifest.pixel_resolution_x, manifest.pixel_resolution_y),
        resolution_unit=manifest.resolution_unit,
        vertical_units=manifest.vertical_units,
        vertical_reference=manifest.vertical_reference,
        nodata=float(manifest.nodata) if manifest.nodata is not None else None,
        license=manifest.license,
        attribution=manifest.attribution,
        processing_status=manifest.processing_status,
    )


def build_evidence_passport(context: CandidateEvidenceContext) -> AnalogueEvidencePassport:
    report = context.discovery_report
    candidate = context.candidate
    bridge = context.scale_bridge
    assessment = build_candidate_assessment(context)
    assessment_findings = {item.conclusion_id: item for item in assessment.conclusions}

    feature_evidence: dict[FeatureName, FeatureAssessmentEvidence] = {}
    for raw_feature, comparison in candidate.feature_comparisons.items():
        feature = cast(FeatureName, raw_feature)
        finding = assessment_findings.get(f"terrain-{feature}")
        status = finding.evidence_status if finding is not None else "INSUFFICIENT_EVIDENCE"
        interpretation = (
            finding.evidence_interpretation
            if finding is not None
            else "No deterministic assessment finding is available for this feature."
        )
        feature_evidence[feature] = FeatureAssessmentEvidence(
            feature=feature,
            evidence_status=status,  # type: ignore[arg-type]
            interpretation=interpretation,
            comparison=comparison,
            dataset_ids={
                "planetary": report.planetary_dataset_id,
                "earth": report.earth_dataset_id,
            },
            source_discovery_run_id=report.run_id,
        )

    missing_evidence: list[str] = list(candidate.missing_features)
    missing_evidence.extend(
        f"additional evidence unavailable: {name.replace('_', ' ')}"
        for name in context.profile.additional_evidence_required
    )
    if (
        context.terrain_twin is None
        or context.terrain_twin.validation_status != "validated"
        or context.terrain_twin.validation_metrics is None
    ):
        missing_evidence.append("independent terrain reconstruction validation")
    limitations = list(
        dict.fromkeys(
            [
                *context.profile.known_limitations,
                *report.warnings,
                *candidate.warnings,
                *bridge.get("warnings", []),
            ]
        )
    )

    scale_bridge = PassportScaleBridge(
        run_id=report.scale_bridge_run_id,
        target_resolution_m=float(bridge["target_resolution_m"]),
        target_resolution_basis=str(bridge["target_resolution_basis"]),
        resampling=str(bridge["resampling"]),
        information_loss=bridge["information_loss"],
        actual_support_width_m=float(bridge["actual_support_width_m"]),
        actual_support_height_m=float(bridge["actual_support_height_m"]),
        coverage={
            key: None if value is None else float(value)
            for key, value in bridge["coverage"].items()
        },
        vertical_comparison_status=str(bridge["vertical_comparison"]),
        vertical_normalization=str(bridge["vertical_normalization"]),
    )
    feature_uncertainties = {
        cast(FeatureName, key): value.distance_standard_error
        for key, value in candidate.feature_comparisons.items()
    }
    reproducibility_inputs = [
        f"discovery-report:{report.run_id}:{context.discovery_report_sha256}",
        f"scale-bridge-report:{report.scale_bridge_run_id}:{context.scale_bridge_report_sha256}",
        f"mission-profile:{context.profile.profile_id}:{context.profile.version}:{context.profile_sha256}",
        *[
            f"dataset-manifest:{dataset_id}:{digest}"
            for dataset_id, digest in sorted(
                (
                    context.manifests[key].id,
                    context.manifest_sha256[key],
                )
                for key in ("planetary", "earth")
            )
        ],
    ]
    if context.terrain_twin is not None:
        reproducibility_inputs.append(
            f"terrain-twin:{context.terrain_twin.terrain_twin_id}:"
            f"{context.terrain_twin_metadata_sha256}"
        )
        if context.terrain_mesh_sha256:
            reproducibility_inputs.append(
                f"terrain-mesh:{context.terrain_twin.terrain_twin_id}:{context.terrain_mesh_sha256}"
            )
    digest_payload = {
        "schema_version": "1.0.0",
        "candidate_id": candidate.candidate_id,
        "discovery_run_id": report.run_id,
        "discovery_report_sha256": context.discovery_report_sha256,
        "scale_bridge_report_sha256": context.scale_bridge_report_sha256,
        "manifest_sha256": context.manifest_sha256,
        "profile_sha256": context.profile_sha256,
        "terrain_twin_metadata_sha256": context.terrain_twin_metadata_sha256,
        "terrain_mesh_sha256": context.terrain_mesh_sha256,
    }
    reproducibility_sha256 = _sha256_json(digest_payload)
    passport_id = reproducibility_sha256[:24]
    planetary = context.manifests["planetary"]
    return AnalogueEvidencePassport(
        passport_schema_version="1.0.0",
        passport_id=passport_id,
        created_at_utc=datetime.now(UTC),
        reproducibility_sha256=reproducibility_sha256,
        candidate=PassportCandidate(
            candidate_id=candidate.candidate_id,
            discovery_run_id=report.run_id,
            discovery_status=candidate.status,
            ranking=candidate.ranking,
            centroid_wgs84=candidate.centroid_wgs84,
            geographic_boundary_wgs84=candidate.geographic_boundary_wgs84,
            evidence_coverage=candidate.evidence_coverage,
        ),
        planetary_reference=PassportPlanetaryReference(
            body=planetary.target_body,  # type: ignore[arg-type]
            product=report.planetary_source_product,
            dataset_id=report.planetary_dataset_id,
            reference_boundary_body_lon_lat=report.planetary_reference_boundary_body_lon_lat,
            coordinate_body=report.planetary_reference_coordinate_body,
            width_m=report.planetary_reference_width_m,
            height_m=report.planetary_reference_height_m,
            effective_resolution_m=report.planetary_effective_resolution_m,
            effective_resolution_status=(
                "reported" if report.planetary_effective_resolution_m is not None else "unavailable"
            ),
        ),
        mission_profile=context.profile,
        source_datasets=[
            _dataset_source(context, "planetary"),
            _dataset_source(context, "earth"),
        ],
        feature_evidence=feature_evidence,
        weighted_distance=PassportWeightedDistance(
            value=candidate.weighted_distance,
            standard_error=candidate.weighted_distance_standard_error,
            interpretation=(
                "Not computed because one or more required feature evidence gates failed; "
                "no rank was assigned. A weighted distance is not a suitability or safety score."
                if candidate.weighted_distance is None
                else "Lower is closer only under this run's configured features and provisional "
                "weights; this is not suitability."
            ),
            method=(
                "Copied from the discovery report without recalculation."
                if candidate.weighted_distance is not None
                else "Weighted mean of normalized feature distances is withheld when required "
                "evidence gates fail."
            ),
        ),
        evidence_coverage=PassportCoverage(
            overall=candidate.evidence_coverage,
            required_features=candidate.required_features,
            available_features=candidate.available_features,
            missing_features=candidate.missing_features,
            by_feature={
                cast(FeatureName, key): value for key, value in candidate.feature_coverage.items()
            },
            planetary_by_feature={
                cast(FeatureName, key): value
                for key, value in candidate.planetary_feature_coverage.items()
            },
            earth_by_feature={
                cast(FeatureName, key): value
                for key, value in candidate.earth_feature_coverage.items()
            },
            minimum_required_coverage=report.config.minimum_evidence_coverage,
            minimum_required_samples_per_surface=report.config.minimum_feature_samples,
        ),
        uncertainty=PassportUncertainty(
            method=report.uncertainty_method,
            feature_distance_standard_errors=feature_uncertainties,
            instrument_or_dem_measurement_uncertainty="unavailable",
            interpretation=(
                "Reported bootstrap standard errors represent finite-sample variability of "
                "feature distances only. "
                "They do not quantify DEM or instrument measurement uncertainty."
            ),
        ),
        terrain_twin=context.terrain_twin,
        terrain_twin_mesh_sha256=context.terrain_mesh_sha256,
        terrain_twin_validation_status=(
            context.terrain_twin.validation_status
            if context.terrain_twin and context.terrain_twin.validation_metrics is not None
            else "unvalidated"
            if context.terrain_twin
            else "unavailable"
        ),
        assessment=assessment,
        missing_evidence=list(dict.fromkeys(missing_evidence)),
        limitations=limitations,
        processing=PassportProcessing(
            discovery_engine_version=report.engine_version,
            discovery_configuration=report.config,
            discovery_processing_configuration_sha256=candidate.processing_configuration_sha256,
            scale_bridge=scale_bridge,
            terrain_analytics_run_ids={
                "planetary": report.planetary_analytics_run_id,
                "earth": report.earth_analytics_run_id,
            },
            profile_configuration_sha256=context.profile_sha256,
            terrain_twin_engine_version=(
                context.terrain_twin.software.get("engine") if context.terrain_twin else None
            ),
        ),
        provenance=PassportProvenance(
            discovery_report_sha256=context.discovery_report_sha256,
            scale_bridge_report_sha256=context.scale_bridge_report_sha256,
            dataset_manifest_sha256={
                context.manifests[key].id: context.manifest_sha256[key]
                for key in ("planetary", "earth")
            },
            terrain_twin_metadata_sha256=context.terrain_twin_metadata_sha256,
            terrain_mesh_sha256=context.terrain_mesh_sha256,
            reproducibility_inputs=reproducibility_inputs,
        ),
    )


def get_evidence_passport(candidate_id: str, profile_id: str) -> AnalogueEvidencePassport:
    return build_evidence_passport(load_candidate_evidence(candidate_id, profile_id))
