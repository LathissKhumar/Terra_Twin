"""Run ScaleBridge using an ingested planetary reference and Earth elevation product."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.domain.schemas.datasets import DatasetManifest
from app.engines.scale_bridge.engine import ObservationCountSource, run_scale_bridge
from app.services.dataset_service import ingest_mola_observation_counts


def find_product(data_dir: Path, product_id: str) -> tuple[DatasetManifest, Path, Path | None]:
    for manifest_file in sorted((data_dir / "manifests").glob("*.json")):
        manifest = DatasetManifest.model_validate_json(manifest_file.read_text())
        if manifest.product_metadata.get("product_id") != product_id:
            continue
        candidates = sorted((data_dir / "raw" / manifest.target_body).glob(manifest.id + ".*"))
        if not candidates:
            raise FileNotFoundError(f"Raw raster for product {product_id} is missing")
        raster = candidates[0]
        label_name = manifest.product_metadata.get("tile_label")
        label = raster.parent / str(label_name) if label_name else None
        if label is not None and not label.is_file():
            raise FileNotFoundError(f"Detached raster label for {product_id} is missing")
        return manifest, raster, label
    raise FileNotFoundError(f"No ingested manifest found for product {product_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mars-product-id", default="MEGT44N000HB")
    parser.add_argument("--earth-product-id", default="COP-DEM-GLO30-18-77")
    parser.add_argument("--mars-center", type=float, nargs=2, required=True, metavar=("LON", "LAT"))
    parser.add_argument(
        "--earth-center", type=float, nargs=2, required=True, metavar=("LON", "LAT")
    )
    parser.add_argument("--support-width-m", type=float, required=True)
    parser.add_argument("--support-height-m", type=float, required=True)
    parser.add_argument("--planetary-support-width-m", type=float)
    parser.add_argument("--planetary-support-height-m", type=float)
    parser.add_argument("--target-resolution-m", type=float)
    parser.add_argument(
        "--use-mola-observation-counts",
        action="store_true",
        help=(
            "Acquire/apply the official co-registered MOLA counts map for "
            "direct-observation support."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data" / "processed" / "scale_bridge",
    )
    args = parser.parse_args()
    data_dir = Path(__file__).resolve().parents[2] / "data"
    mars_manifest, mars_raster, mars_label = find_product(data_dir, args.mars_product_id)
    earth_manifest, earth_raster, earth_label = find_product(data_dir, args.earth_product_id)
    observation_counts = None
    if args.use_mola_observation_counts:
        counts_path, counts_label, counts_manifest = ingest_mola_observation_counts(
            data_dir, mars_manifest
        )
        observation_counts = ObservationCountSource(
            raster_path=counts_path,
            open_path=counts_label,
            manifest=counts_manifest,
        )
    result = run_scale_bridge(
        planetary_raster=mars_raster,
        planetary_open_path=mars_label,
        planetary_manifest=mars_manifest,
        planetary_center=tuple(args.mars_center),
        earth_raster=earth_raster,
        earth_open_path=earth_label,
        planetary_observation_counts=observation_counts,
        earth_manifest=earth_manifest,
        earth_center=tuple(args.earth_center),
        support_width_m=args.support_width_m,
        support_height_m=args.support_height_m,
        planetary_support_width_m=args.planetary_support_width_m,
        planetary_support_height_m=args.planetary_support_height_m,
        output_dir=args.output_dir,
        target_resolution_m=args.target_resolution_m,
    )
    print(json.dumps(result.report.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
