"""Readable PDF rendering of the canonical Analogue Evidence Passport."""

from __future__ import annotations

from html import escape
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.domain.schemas.evidence_passport import AnalogueEvidencePassport

_PAGE_LIMIT_BYTES = 5_000_000


def _paragraph(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(value)), style)


def render_passport_pdf(passport: AnalogueEvidencePassport) -> bytes:
    """Render the canonical passport fields without taking raw HTML or file paths."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=17 * mm,
        leftMargin=17 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        title=f"TerraTwin Evidence Passport {passport.passport_id}",
        author="TerraTwin",
        pageCompression=1,
    )
    base = getSampleStyleSheet()
    title = ParagraphStyle(
        "TerraTwinTitle",
        parent=base["Title"],
        textColor=colors.HexColor("#0e7490"),
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        alignment=TA_LEFT,
        spaceAfter=9,
    )
    heading = ParagraphStyle(
        "TerraTwinHeading",
        parent=base["Heading2"],
        textColor=colors.HexColor("#164e63"),
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        spaceBefore=9,
        spaceAfter=5,
    )
    body = ParagraphStyle(
        "TerraTwinBody",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11.5,
        spaceAfter=3,
        wordWrap="CJK",
    )
    small = ParagraphStyle("TerraTwinSmall", parent=body, fontSize=7.2, leading=9)
    weighted_distance = passport.weighted_distance.value
    weighted_distance_text = (
        f"{weighted_distance:.6g}" if weighted_distance is not None else "not computed"
    )
    story: list[Any] = [
        _paragraph("TerraTwin Analogue Evidence Passport", title),
        _paragraph(
            f"Passport {passport.passport_id} · schema {passport.passport_schema_version}", body
        ),
        _paragraph(f"Generated (UTC): {passport.created_at_utc.isoformat()}", body),
        _paragraph(f"Reproducibility SHA-256: {passport.reproducibility_sha256}", small),
        Spacer(1, 5),
        _paragraph("Evidence status", heading),
        _paragraph(
            f"Candidate {passport.candidate.candidate_id} from discovery run "
            f"{passport.candidate.discovery_run_id}: {passport.candidate.discovery_status}; "
            f"rank: {passport.candidate.ranking}; overall assessment: "
            f"{passport.assessment.overall_evidence_status}.",
            body,
        ),
        _paragraph(
            f"Evidence coverage: {passport.evidence_coverage.overall:.6f}; required minimum: "
            f"{passport.evidence_coverage.minimum_required_coverage:.3f}. Weighted distance: "
            f"{weighted_distance_text}.",
            body,
        ),
        _paragraph(
            f"Planetary reference: {passport.planetary_reference.body} — "
            f"{passport.planetary_reference.product}. Earth/mesh validation: "
            f"{passport.terrain_twin_validation_status}.",
            body,
        ),
        _paragraph("Candidate location and source datasets", heading),
        _paragraph(
            f"Centroid WGS84 (longitude, latitude): {passport.candidate.centroid_wgs84}; "
            f"candidate boundary vertices: {len(passport.candidate.geographic_boundary_wgs84)}.",
            body,
        ),
    ]
    for source in passport.source_datasets:
        story.append(
            KeepTogether(
                [
                    _paragraph(
                        f"{source.target_body.upper()} — {source.product} "
                        f"({source.version or 'version unavailable'})",
                        body,
                    ),
                    _paragraph(
                        f"Provider: {source.provider}; dataset ID: {source.dataset_id}; "
                        f"CRS: {source.crs}; raster dimensions: {source.dimensions}; "
                        f"pixel spacing: {source.pixel_resolution} {source.resolution_unit}.",
                        small,
                    ),
                    _paragraph(
                        f"Vertical units/reference: {source.vertical_units} / "
                        f"{source.vertical_reference}; "
                        f"raw checksum: {source.raw_checksum_sha256}; "
                        "discovery-processing checksum: "
                        f"{source.discovery_processing_checksum_sha256}.",
                        small,
                    ),
                ]
            )
        )

    story.extend([_paragraph("Terrain feature comparisons", heading)])
    feature_rows: list[list[Any]] = [["Feature", "Status and measurements", "Comparison method"]]
    for name, evidence in passport.feature_evidence.items():
        comparison = evidence.comparison
        reference_median = (
            f"{comparison.reference_median:.6g}"
            if comparison.reference_median is not None
            else "n/a"
        )
        candidate_median = (
            f"{comparison.candidate_median:.6g}"
            if comparison.candidate_median is not None
            else "n/a"
        )
        distance = (
            f"{comparison.normalized_distance:.6g}"
            if comparison.normalized_distance is not None
            else "not computed"
        )
        details = (
            f"{evidence.evidence_status}; samples {comparison.reference_sample_count}/"
            f"{comparison.candidate_sample_count}; coverage "
            f"{comparison.reference_coverage:.6f}/{comparison.candidate_coverage:.6f}; "
            f"normalized distance {distance} {comparison.units}; median "
            f"{reference_median} / {candidate_median}"
        )
        distribution = (
            f"Distribution summaries: planetary {comparison.reference_summary}; "
            f"Earth {comparison.candidate_summary}"
        )
        feature_rows.append(
            [
                _paragraph(name.replace("_", " "), small),
                Paragraph(f"{escape(details)}<br/>{escape(distribution)}", small),
                _paragraph(comparison.method, small),
            ]
        )
    feature_table = Table(feature_rows, colWidths=[31 * mm, 79 * mm, 63 * mm], repeatRows=1)
    feature_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#164e63")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(feature_table)
    story.extend([_paragraph("Terrain Twin validation", heading)])
    if passport.terrain_twin_validation_status == "validated" and passport.terrain_twin:
        metrics: dict[str, object] = (
            passport.terrain_twin.validation_metrics.model_dump()
            if passport.terrain_twin.validation_metrics is not None
            else {}
        )
        story.append(
            _paragraph(
                f"Independent comparison metrics: {metrics}. The reported values do not imply "
                "a universal acceptance threshold or analogue suitability.",
                body,
            )
        )
    else:
        validation_reason = (
            passport.terrain_twin.validation_reason
            if passport.terrain_twin is not None
            else "No Terrain Twin validation record exists."
        )
        story.append(
            _paragraph(
                f"{passport.terrain_twin_validation_status.upper()}: {validation_reason} "
                "No independent accuracy metrics are available.",
                body,
            )
        )
    story.extend([_paragraph("Experiment transferability findings", heading)])
    for conclusion in passport.assessment.conclusions:
        story.append(
            KeepTogether(
                [
                    _paragraph(f"{conclusion.category} · {conclusion.evidence_status}", body),
                    _paragraph(conclusion.conclusion, body),
                    _paragraph(conclusion.evidence_interpretation, small),
                    *[
                        _paragraph(f"Missing: {item}", small)
                        for item in conclusion.missing_information
                    ],
                    *[_paragraph(f"Limit: {item}", small) for item in conclusion.limitations],
                    Spacer(1, 3),
                ]
            )
        )

    story.extend([PageBreak(), _paragraph("Missing evidence and limitations", heading)])
    for item in passport.missing_evidence:
        story.append(_paragraph(f"• {item}", body))
    for item in passport.limitations:
        story.append(_paragraph(f"• {item}", body))
    story.extend(
        [
            _paragraph("Reproducibility", heading),
            _paragraph(
                f"Discovery run {passport.candidate.discovery_run_id}; ScaleBridge run "
                f"{passport.processing.scale_bridge.run_id}; analytics runs "
                f"{passport.processing.terrain_analytics_run_ids}; mission profile "
                f"{passport.mission_profile.profile_id} v{passport.mission_profile.version}; "
                "configuration SHA-256 "
                f"{passport.processing.discovery_processing_configuration_sha256}.",
                body,
            ),
            _paragraph(f"Reproducibility digest: {passport.reproducibility_sha256}", small),
        ]
    )
    for source_ref in passport.provenance.reproducibility_inputs:
        story.append(_paragraph(source_ref, small))
    story.extend(
        [
            _paragraph("Interpretation notice", heading),
            _paragraph(
                "Measurements are copied from stored processing results. Interpretations are "
                "deterministic profile rules. Insufficient observations are not treated as zero. "
                "Terrain similarity "
                "does not guarantee rover safety or performance, and this passport does not assert "
                "universal planetary equivalence.",
                body,
            ),
        ]
    )

    def draw_page_number(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(17 * mm, 10 * mm, f"TerraTwin · {passport.passport_id}")
        canvas.drawRightString(A4[0] - 17 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=draw_page_number, onLaterPages=draw_page_number)
    output = buffer.getvalue()
    if len(output) > _PAGE_LIMIT_BYTES:
        raise ValueError("Rendered evidence passport exceeds the configured PDF size limit")
    if not output.startswith(b"%PDF-"):
        raise RuntimeError("PDF renderer did not produce a valid PDF document")
    return output
