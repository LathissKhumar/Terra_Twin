from __future__ import annotations

from pathlib import Path

from app.services.evidence_pdf import render_passport_pdf
from app.services.evidence_service import build_evidence_passport
from tests.fixtures.assessment_context import build_passport_context


def test_passport_is_reproducible_traceable_and_exposes_missing_evidence(tmp_path: Path) -> None:
    context = build_passport_context(tmp_path)
    first = build_evidence_passport(context)
    second = build_evidence_passport(context)

    assert first.passport_schema_version == "1.0.0"
    assert first.passport_id == second.passport_id
    assert first.reproducibility_sha256 == second.reproducibility_sha256
    assert first.candidate.ranking is None
    assert first.weighted_distance.value is None
    assert first.terrain_twin_validation_status == "unavailable"
    assert len(first.feature_evidence) == len(first.mission_profile.required_features)
    assert (
        first.source_datasets[0].raw_checksum_sha256
        == context.manifests["planetary"].checksum_sha256
    )
    assert (
        first.source_datasets[1].raw_checksum_sha256 == context.manifests["earth"].checksum_sha256
    )
    assert any("soil" in value for value in first.missing_evidence)
    assert any(
        "independent terrain reconstruction validation" in value for value in first.missing_evidence
    )
    assert "not a suitability" in first.weighted_distance.interpretation


def test_pdf_is_a_readable_export_of_canonical_passport(tmp_path: Path) -> None:
    passport = build_evidence_passport(build_passport_context(tmp_path))
    pdf = render_passport_pdf(passport)

    assert pdf.startswith(b"%PDF-")
    assert pdf.endswith(b"%%EOF\n")
    assert len(pdf) < 5_000_000


def test_passport_preserves_undefined_paired_coverage_for_unequal_supports(
    tmp_path: Path,
) -> None:
    context = build_passport_context(tmp_path)
    context.scale_bridge["coverage"] = {
        "planetary_fraction": 1.0,
        "earth_fraction": 1.0,
        "common_fraction": None,
    }
    passport = build_evidence_passport(context)
    assert passport.processing.scale_bridge.coverage == {
        "planetary_fraction": 1.0,
        "earth_fraction": 1.0,
        "common_fraction": None,
    }
