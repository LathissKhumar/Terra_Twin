from app.domain.schemas.analogue_discovery import DiscoveryReport, PlanetaryReferenceWindow
from tests.fixtures.assessment_context import build_candidate_and_report


def test_older_discovery_reports_keep_surface_types_explicitly_unavailable() -> None:
    _, report = build_candidate_and_report()
    payload = report.model_dump(mode="python")
    payload.update(
        planetary_source_sha256="3" * 64,
        earth_source_sha256="4" * 64,
        earth_effective_resolution_m=None,
        planetary_reference_window=PlanetaryReferenceWindow(
            row_off=0,
            col_off=0,
            height=44,
            width=44,
            center_row=22,
            center_col=22,
            requested_width_m=20_372,
            requested_height_m=20_372,
            actual_width_m=20_372,
            actual_height_m=20_372,
        ),
        candidate_width_cells=44,
        candidate_height_cells=44,
        actual_candidate_width_m=20_372,
        actual_candidate_height_m=20_372,
        actual_stride_x_m=10_000,
        actual_stride_y_m=10_000,
    )
    payload.pop("planetary_surface_type", None)
    payload.pop("earth_surface_type", None)

    restored = DiscoveryReport.model_validate(payload)

    assert restored.planetary_surface_type is None
    assert restored.earth_surface_type is None
