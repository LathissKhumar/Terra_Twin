"""Run a bounded Mars-to-Earth terrain-window search from validated local outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import settings
from app.domain.schemas.analogue_discovery import DiscoveryConfig
from app.engines.analogue_discovery import load_mission_profile, run_discovery


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale-bridge-run-id", default="4b76a5af44a9658065a4")
    parser.add_argument("--mars-analytics-run-id", default="4aa2a0f6cc4cd73fa047")
    parser.add_argument("--earth-analytics-run-id", default="5cbea74eb4a9a04afd3b")
    parser.add_argument("--candidate-width-m", type=float, default=20_000)
    parser.add_argument("--candidate-height-m", type=float, default=20_000)
    parser.add_argument("--candidate-stride-m", type=float, default=10_000)
    parser.add_argument("--minimum-evidence-coverage", type=float, default=0.8)
    parser.add_argument("--minimum-feature-samples", type=int, default=20)
    parser.add_argument("--maximum-candidate-count", type=int, default=10_000)
    parser.add_argument(
        "--analytics-root",
        type=Path,
        default=settings.DATA_DIR / "derived" / "terrain_analytics_50km",
        help="Directory containing the specified Mars and Earth analytics run folders.",
    )
    parser.add_argument("--search-boundary-wgs84", type=float, nargs=4)
    parser.add_argument(
        "--mission-profile",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "config"
        / "mission_profiles"
        / "rover_mobility_and_terrain_navigation.v1.json",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=settings.DATA_DIR / "results" / "analogue_discovery"
    )
    args = parser.parse_args()

    scale_dir = settings.DATA_DIR / "processed" / "scale_bridge" / args.scale_bridge_run_id
    analytics_root = args.analytics_root
    if not analytics_root.is_absolute():
        analytics_root = settings.DATA_DIR.parent / analytics_root
    mars_dir = analytics_root / "mars" / args.mars_analytics_run_id
    earth_dir = analytics_root / "earth" / args.earth_analytics_run_id
    config = DiscoveryConfig(
        candidate_width_m=args.candidate_width_m,
        candidate_height_m=args.candidate_height_m,
        candidate_stride_m=args.candidate_stride_m,
        minimum_evidence_coverage=args.minimum_evidence_coverage,
        minimum_feature_samples=args.minimum_feature_samples,
        maximum_candidate_count=args.maximum_candidate_count,
        search_boundary_wgs84=(
            tuple(args.search_boundary_wgs84) if args.search_boundary_wgs84 else None
        ),
    )
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = settings.DATA_DIR.parent / output_dir

    report = run_discovery(
        planetary_feature_dir=mars_dir,
        planetary_analytics_report=mars_dir / "report.json",
        earth_feature_dir=earth_dir,
        earth_analytics_report=earth_dir / "report.json",
        planetary_relative_dem=scale_dir / "planetary_relative_elevation.tif",
        earth_relative_dem=scale_dir / "earth_relative_elevation.tif",
        scale_bridge_report_path=scale_dir / "report.json",
        output_dir=output_dir,
        config=config,
        mission_profile=load_mission_profile(args.mission_profile),
    )
    print(
        json.dumps(
            {
                "report_path": str(output_dir / report.run_id / "report.json"),
                "run_id": report.run_id,
                "reproducibility_sha256": report.reproducibility_sha256,
                "search_boundary_wgs84": report.search_boundary_wgs84,
                "generated_window_count": report.generated_window_count,
                "evaluated_window_count": report.evaluated_window_count,
                "eligible_candidate_count": report.eligible_candidate_count,
                "ranked_candidate_count": report.ranked_candidate_count,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
