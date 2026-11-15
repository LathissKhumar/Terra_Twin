"""Mission profiles and data-backed planetary reference choices."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.config import BACKEND_DIR, settings
from app.domain.schemas.datasets import DatasetManifest
from app.domain.schemas.scale_bridge import ScaleBridgeReport

router = APIRouter(prefix="/missions", tags=["Missions"])
_PROFILE_ID = "ROVER_MOBILITY_AND_TERRAIN_NAVIGATION"
_DISCOVERY_PROFILE_PATH = (
    BACKEND_DIR / "config" / "mission_profiles" / "rover_mobility_and_terrain_navigation.v1.json"
)


def _manifests() -> list[DatasetManifest]:
    output: list[DatasetManifest] = []
    for path in sorted(settings.manifests_dir.glob("*.json")):
        try:
            output.append(DatasetManifest.model_validate_json(path.read_text()))
        except (OSError, ValueError):
            continue
    return output


def _last_center_for_dataset(dataset_id: str, body: str) -> list[float] | None:
    report_root = settings.processed_data_dir / "scale_bridge"
    for path in sorted(
        report_root.glob("*/report.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True
    ):
        try:
            report = ScaleBridgeReport.model_validate_json(path.read_text())
        except (OSError, ValueError):
            continue
        source = report.planetary if body == "planetary" else report.earth
        if source.dataset_id == dataset_id:
            return list(source.center_longitude_latitude)
    return None


@router.get("")
def list_missions() -> dict[str, Any]:
    """Expose only profiles and sources discoverable from installed data/manifests."""
    try:
        profile = json.loads(_DISCOVERY_PROFILE_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=503, detail="Configured mission profile is unavailable"
        ) from exc
    manifests = _manifests()
    planetary = [
        item
        for item in manifests
        if item.target_body == "mars"
        and item.product_metadata.get("product_id")
        in {"MEGT44N000HB", "DTEEC_048842_1985_048908_1985_U01"}
    ]
    supported_bodies = ["mars"] if planetary else []
    if any(item.target_body == "moon" for item in manifests):
        supported_bodies.append("moon")
    hi_res_reference = next(
        (
            item
            for item in planetary
            if str(item.product_metadata.get("product_id", "")).startswith("DTEEC_")
        ),
        None,
    )
    default_reference = next(
        (item for item in planetary if item.product_metadata.get("product_id") == "MEGT44N000HB"),
        None,
    )
    reference_dataset = hi_res_reference or default_reference
    regions: list[dict[str, Any]] = [
        {
            "region_id": "jezero_crater",
            "label": "Jezero Crater, Mars",
            "body": "mars",
            "source_dataset_ids": [item.id for item in planetary],
            "coverage_status": "available" if planetary else "source_required",
            "default_center_source": (
                "previous_scale_bridge_run"
                if reference_dataset and _last_center_for_dataset(reference_dataset.id, "planetary")
                else "HiRISE DTM product center"
                if hi_res_reference
                else "manual center required"
            ),
            "last_processed_center_lon_lat": (
                _last_center_for_dataset(reference_dataset.id, "planetary")
                if reference_dataset and _last_center_for_dataset(reference_dataset.id, "planetary")
                else [77.52, 18.46]
                if hi_res_reference
                else None
            ),
            "coverage": [item.bounds for item in planetary],
            "description": (
                "Jezero reference sources include the HiRISE stereo DTM and MOLA MEGDR; "
                "the default center is the HiRISE product center when that DTM is installed."
            ),
        }
    ]
    moon_manifests = [item for item in manifests if item.target_body == "moon"]
    regions.extend(
        {
            "region_id": f"moon_dataset_{item.id[:12]}",
            "label": f"User-defined lunar reference · {item.product}",
            "body": "moon",
            "source_dataset_ids": [item.id],
            "coverage_status": "available",
            "default_center_source": "manual_center_required",
            "last_processed_center_lon_lat": _last_center_for_dataset(item.id, "planetary"),
            "coverage": [item.bounds],
            "description": "Reference center must be selected inside this validated lunar raster.",
        }
        for item in moon_manifests
    )
    earth_datasets = [item for item in manifests if item.target_body == "earth"]
    return {
        "mission_profiles": [profile],
        "supported_bodies": supported_bodies,
        "reference_regions": regions,
        "earth_search_defaults": [
            {
                "dataset_id": item.id,
                "last_processed_center_lon_lat": _last_center_for_dataset(item.id, "earth"),
            }
            for item in earth_datasets
        ],
        "dataset_count": len(manifests),
        "unavailable_bodies": [body for body in ("mars", "moon") if body not in supported_bodies],
    }
