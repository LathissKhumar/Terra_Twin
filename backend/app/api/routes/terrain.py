"""Candidate comparison reports and visualization-only feature-map previews."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Literal

import numpy as np
import rasterio
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from pyproj import CRS
from rasterio.enums import Resampling
from rasterio.windows import Window

from app.core.config import settings
from app.domain.schemas.analogue_discovery import (
    CandidateResult,
    CandidateWindow,
    DiscoveryReport,
    FeatureName,
    PlanetaryReferenceWindow,
)
from app.domain.schemas.scale_bridge import ScaleBridgeReport, SourceGridReport
from app.domain.schemas.terrain_analytics import TerrainAnalyticsReport
from app.services.discovery_results import report_for_candidate

router = APIRouter(prefix="/terrain", tags=["Terrain Comparison"])
_FEATURES: tuple[FeatureName, ...] = (
    "slope",
    "local_relief",
    "terrain_roughness",
    "profile_curvature",
    "plan_curvature",
    "topographic_position_index",
    "landform_morphology",
)
_CONTINUOUS_COLORS = np.array(
    [[17, 58, 93], [20, 135, 166], [53, 191, 171], [236, 190, 88], [232, 106, 76]],
    dtype="uint8",
)
_LANDFORM_COLORS = {-1: (38, 119, 176), 0: (107, 131, 139), 1: (232, 161, 68)}


def _report_by_run(run_id: str) -> DiscoveryReport:
    if len(run_id) != 20 or any(char not in "0123456789abcdef" for char in run_id):
        raise HTTPException(404, "Discovery run was not found")
    path = settings.results_dir / "analogue_discovery" / run_id / "report.json"
    try:
        return DiscoveryReport.model_validate_json(path.read_text())
    except (OSError, ValueError) as exc:
        raise HTTPException(404, "Discovery run was not found or is invalid") from exc


def _scale_bridge_report(run_id: str) -> ScaleBridgeReport:
    if len(run_id) != 20 or any(char not in "0123456789abcdef" for char in run_id):
        raise HTTPException(404, "ScaleBridge run was not found")
    path = settings.processed_data_dir / "scale_bridge" / run_id / "report.json"
    try:
        return ScaleBridgeReport.model_validate_json(path.read_text())
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Stored ScaleBridge provenance is unavailable") from exc


def _source_crs_label(value: str) -> str:
    try:
        crs = CRS.from_user_input(value)
        authority = crs.to_authority()
        return f"{crs.name} ({authority[0]}:{authority[1]})" if authority else crs.name
    except Exception:
        return "Custom planetary coordinate system"


def _local_crs_label(grid: SourceGridReport, body: str) -> str:
    center = grid.center_longitude_latitude
    longitude, latitude = center
    lon_hemi = "E" if longitude >= 0 else "W"
    lat_hemi = "N" if latitude >= 0 else "S"
    try:
        source_crs = CRS.from_user_input(grid.source_crs)
        geodetic_crs = source_crs.geodetic_crs
        ellipsoid_def = geodetic_crs.ellipsoid if geodetic_crs is not None else None
        ellipsoid = (
            ellipsoid_def.name if ellipsoid_def is not None else f"{body} reference ellipsoid"
        )
    except Exception:
        ellipsoid = f"{body.title()} reference ellipsoid"
    return (
        "Local Azimuthal Equidistant (metres), centered "
        f"{abs(latitude):.5f}°{lat_hemi}, {abs(longitude):.5f}°{lon_hemi} "
        f"on {ellipsoid}"
    )


def _find_candidate(candidate_id: str) -> tuple[DiscoveryReport, CandidateResult]:
    _, payload = report_for_candidate(candidate_id)
    try:
        report = DiscoveryReport.model_validate(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=503, detail="Candidate discovery report is invalid"
        ) from exc
    candidate = next(item for item in report.candidates if item.candidate_id == candidate_id)
    return report, candidate


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: str) -> dict[str, object]:
    report, candidate = _find_candidate(candidate_id)
    return {
        "candidate": candidate.model_dump(mode="json"),
        "discovery_run_id": report.run_id,
        "planetary_dataset_id": report.planetary_dataset_id,
        "earth_dataset_id": report.earth_dataset_id,
        "planetary_product": report.planetary_source_product,
        "earth_product": report.earth_source_product,
        "mission_profile": report.mission_profile.model_dump(mode="json"),
        "searched_boundary_wgs84": report.search_boundary_wgs84,
        "warnings": list(dict.fromkeys([*report.warnings, *candidate.warnings])),
    }


@router.get("/candidates/{candidate_id}/comparison")
def get_candidate_comparison(candidate_id: str) -> dict[str, object]:
    report, candidate = _find_candidate(candidate_id)
    scale = _scale_bridge_report(report.scale_bridge_run_id)
    feature_maps: dict[str, dict[str, str]] = {}
    for feature in _FEATURES:
        feature_maps[feature] = {
            "mars_preview_url": (
                f"/api/v1/terrain/discovery-runs/{report.run_id}/features/mars/{feature}/preview/{candidate.candidate_id}"
            ),
            "earth_preview_url": (
                f"/api/v1/terrain/discovery-runs/{report.run_id}/features/earth/{feature}/preview/{candidate.candidate_id}"
            ),
        }
    return {
        "candidate": candidate.model_dump(mode="json"),
        "discovery_run_id": report.run_id,
        "planetary_reference": {
            "body": report.planetary_reference_coordinate_body,
            "product": report.planetary_source_product,
            "dataset_id": report.planetary_dataset_id,
            "reference_boundary_body_lon_lat": report.planetary_reference_boundary_body_lon_lat,
            "effective_resolution_m": report.planetary_effective_resolution_m,
        },
        "earth_source": {
            "product": report.earth_source_product,
            "dataset_id": report.earth_dataset_id,
            "effective_resolution_m": report.earth_effective_resolution_m,
        },
        "comparison_support": {
            "pixel_width_m": report.earth_pixel_width_m,
            "pixel_height_m": report.earth_pixel_height_m,
            "scale_bridge_run_id": report.scale_bridge_run_id,
            "target_resolution_m": scale.target_resolution_m,
            "target_resolution_basis": scale.target_resolution_basis,
            "resampling": scale.resampling,
            "information_loss": scale.information_loss,
            "coverage": scale.coverage.model_dump(mode="json"),
            "planetary_crs": _local_crs_label(scale.planetary, "Mars"),
            "earth_crs": _local_crs_label(scale.earth, "Earth"),
            "planetary_source_crs": _source_crs_label(scale.planetary.source_crs),
            "earth_source_crs": _source_crs_label(scale.earth.source_crs),
            "vertical_comparison": scale.vertical_comparison,
            "warning": (
                "Mars and Earth maps use independent local metric CRSs; matching array indices "
                "pair support only."
            ),
        },
        "source_resolution": {
            "planetary_nominal_ground_spacing_m": [
                scale.planetary.nominal_ground_spacing_x_m,
                scale.planetary.nominal_ground_spacing_y_m,
            ],
            "planetary_effective_resolution_m": scale.planetary.effective_resolution_m,
            "earth_nominal_ground_spacing_m": [
                scale.earth.nominal_ground_spacing_x_m,
                scale.earth.nominal_ground_spacing_y_m,
            ],
            "earth_effective_resolution_m": scale.earth.effective_resolution_m,
        },
        "features": candidate.feature_comparisons,
        "feature_maps": feature_maps,
        "coverage": {
            "overall": candidate.evidence_coverage,
            "planetary_by_feature": candidate.planetary_feature_coverage,
            "earth_by_feature": candidate.earth_feature_coverage,
            "minimum_required_coverage": report.config.minimum_evidence_coverage,
        },
        "warnings": list(dict.fromkeys([*report.warnings, *candidate.warnings])),
    }


def _analytics_report(run_id: str, body: str) -> tuple[TerrainAnalyticsReport, Path]:
    if len(run_id) != 20 or any(char not in "0123456789abcdef" for char in run_id):
        raise HTTPException(404, "Terrain analytics run was not found")
    directory = settings.derived_data_dir / "terrain_analytics" / body / run_id
    report_path = directory / "report.json"
    try:
        report = TerrainAnalyticsReport.model_validate_json(report_path.read_text())
    except (OSError, ValueError) as exc:
        raise HTTPException(404, "Terrain analytics artifact is unavailable") from exc
    if report.target_body != body:
        raise HTTPException(404, "Terrain analytics source body does not match")
    return report, directory


@router.get("/discovery-runs/{run_id}/features/{body}/{feature}/preview/{candidate_id}")
def get_feature_map_preview(
    run_id: str,
    body: Literal["mars", "earth"],
    feature: FeatureName,
    candidate_id: str,
) -> Response:
    discovery = _report_by_run(run_id)
    candidate = next(
        (item for item in discovery.candidates if item.candidate_id == candidate_id), None
    )
    if candidate is None:
        raise HTTPException(404, "Candidate is not part of this discovery run")
    analytics_run_id = (
        discovery.planetary_analytics_run_id if body == "mars" else discovery.earth_analytics_run_id
    )
    analytics, directory = _analytics_report(analytics_run_id, body)
    feature_report = analytics.features.get(feature)
    if feature_report is None:
        raise HTTPException(404, "Feature map is unavailable for this run")
    filename = Path(feature_report.raster_file).name
    if filename != f"{feature}.tif":
        raise HTTPException(503, "Feature map artifact metadata is invalid")
    raster_path = (directory / filename).resolve()
    if not raster_path.is_relative_to(directory.resolve()) or not raster_path.is_file():
        raise HTTPException(404, "Feature map artifact is unavailable")
    if body == "mars":
        window_spec: CandidateWindow | PlanetaryReferenceWindow = (
            discovery.planetary_reference_window
        )
    else:
        window_spec = candidate.window
    window = Window(window_spec.col_off, window_spec.row_off, window_spec.width, window_spec.height)
    with rasterio.open(raster_path) as dataset:
        if (
            window.col_off + window.width > dataset.width
            or window.row_off + window.height > dataset.height
        ):
            raise HTTPException(503, "Candidate window is outside its feature raster")
        out_height = min(1024, int(window.height))
        out_width = min(1024, int(window.width))
        output_shape = (out_height, out_width)
        resampling = Resampling.nearest if feature == "landform_morphology" else Resampling.average
        values = dataset.read(
            1, window=window, out_shape=output_shape, resampling=resampling
        ).astype("float64")
        valid = (
            dataset.read_masks(
                1, window=window, out_shape=output_shape, resampling=Resampling.nearest
            )
            > 0
        )
        valid &= np.isfinite(values)
        rgba = np.zeros((*values.shape, 4), dtype="uint8")
        if feature == "landform_morphology":
            classes = np.rint(values).astype("int8")
            for class_code, color in _LANDFORM_COLORS.items():
                selected = valid & (classes == class_code)
                rgba[selected, :3] = color
            display_range: dict[str, object] = {
                "categories": _LANDFORM_COLORS,
                "kind": "categorical",
            }
        elif np.any(valid):
            minimum = float(np.percentile(values[valid], 5))
            maximum = float(np.percentile(values[valid], 95))
            if maximum <= minimum:
                maximum = minimum + max(abs(minimum) * 1e-9, 1e-9)
            scaled = np.clip((values - minimum) / (maximum - minimum), 0, 1)
            segment = scaled * (len(_CONTINUOUS_COLORS) - 1)
            lower = np.minimum(segment.astype("int32"), len(_CONTINUOUS_COLORS) - 2)
            fraction = segment - lower
            colors = (
                _CONTINUOUS_COLORS[lower] * (1 - fraction[..., None])
                + _CONTINUOUS_COLORS[lower + 1] * fraction[..., None]
            ).astype("uint8")
            rgba[valid, :3] = colors[valid]
            display_range = {
                "minimum_p05": minimum,
                "maximum_p95": maximum,
                "kind": "continuous",
            }
        else:
            display_range = {"kind": "unavailable", "reason": "No valid pixels"}
        rgba[valid, 3] = 255
        image = Image.fromarray(rgba, mode="RGBA")
        output = BytesIO()
        metadata = PngInfo()
        metadata.add_text("feature", feature)
        metadata.add_text("body", body)
        metadata.add_text("display_range", str(display_range))
        image.save(output, format="PNG", pnginfo=metadata, optimize=True)
        width, height = dataset.width, dataset.height
        nodata_fraction = 1 - float(valid.sum() / valid.size)
    return Response(
        content=output.getvalue(),
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-TerraTwin-Feature": feature,
            "X-TerraTwin-Source-Valid-Fraction": f"{1 - nodata_fraction:.8f}",
            "X-TerraTwin-Raster-Shape": f"{width}x{height}",
            "X-TerraTwin-Display-Range": str(display_range),
        },
    )
