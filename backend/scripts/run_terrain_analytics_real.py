"""Produce reproducible terrain-feature maps from a real ScaleBridge run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import settings
from app.domain.schemas.terrain_analytics import TerrainAnalyticsConfig
from app.engines.terrain_analytics import analyze_terrain_raster


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scale-bridge-run-id",
        default="e2fe8955610bb112c46f",
        help="Existing ScaleBridge run ID containing both harmonized relative DEMs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=settings.DATA_DIR / "derived" / "terrain_analytics",
    )
    parser.add_argument("--neighborhood-radius-m", type=float, default=463.0)
    parser.add_argument("--minimum-neighborhood-valid-fraction", type=float, default=0.8)
    parser.add_argument(
        "--landform-standardization-scale-m",
        type=float,
        help="Shared TPI scale in metres. Defaults to the Mars feature raster's TPI SD for both bodies.",
    )
    args = parser.parse_args()
    run_dir = settings.DATA_DIR / "processed" / "scale_bridge" / args.scale_bridge_run_id
    if not run_dir.is_dir():
        parser.error(f"ScaleBridge run directory does not exist: {run_dir}")
    config = TerrainAnalyticsConfig(
        neighborhood_radius_m=args.neighborhood_radius_m,
        minimum_neighborhood_valid_fraction=args.minimum_neighborhood_valid_fraction,
        landform_standardization_scale_m=args.landform_standardization_scale_m,
    )
    output_root = Path(args.output_dir)
    if not output_root.is_absolute():
        output_root = settings.DATA_DIR.parent / output_root
    reports = {}
    mars_reference_tpi_scale = args.landform_standardization_scale_m
    for body, input_name in (
        ("mars", "planetary_relative_elevation.tif"),
        ("earth", "earth_relative_elevation.tif"),
    ):
        body_config = config
        if body == "earth":
            if mars_reference_tpi_scale is None:
                mars_reference_tpi_scale = reports["mars"]["features"][
                    "topographic_position_index"
                ]["summary"]["standard_deviation"]
            body_config = config.model_copy(
                update={"landform_standardization_scale_m": mars_reference_tpi_scale}
            )
        result = analyze_terrain_raster(
            run_dir / input_name,
            output_root / body,
            body_config,
        )
        reports[body] = result.report.model_dump(mode="json")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
