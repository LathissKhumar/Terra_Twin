"""Create compact, source-derived raster samples for the ingestion test suite."""

import json
from pathlib import Path

import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import Window

from app.core.config import settings
from app.engines.data_ingestion.ingestion import sha256_file

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "data"
SAMPLE_SIZE = 64


def write_sample(
    source_path: Path,
    open_path: Path,
    output_path: Path,
    lon: float,
    lat: float,
    provenance: dict[str, str],
):
    with rasterio.open(open_path) as source:
        if source.crs.is_geographic:
            row, column = source.index(lon, lat)
        else:
            transformer = Transformer.from_crs(
                CRS.from_wkt(source.crs.to_wkt()).geodetic_crs,
                CRS.from_wkt(source.crs.to_wkt()),
                always_xy=True,
            )
            x, y = transformer.transform(lon, lat)
            row, column = source.index(x, y)
        col_off = max(0, min(column - SAMPLE_SIZE // 2, source.width - SAMPLE_SIZE))
        row_off = max(0, min(row - SAMPLE_SIZE // 2, source.height - SAMPLE_SIZE))
        window = Window(col_off, row_off, SAMPLE_SIZE, SAMPLE_SIZE)
        profile = source.profile.copy()
        profile.update(
            driver="GTiff",
            width=SAMPLE_SIZE,
            height=SAMPLE_SIZE,
            transform=source.window_transform(window),
            compress="LZW",
        )
        with rasterio.open(output_path, "w", **profile) as sample:
            sample.write(source.read(1, window=window).copy(), 1)
            sample.update_tags(
                source_sha256=sha256_file(source_path),
                source_filename=source_path.name,
                window_col_offset=int(col_off),
                window_row_offset=int(row_off),
                sample_note="Exact source raster window; no elevation values synthesized",
            )
    return {
        "path": output_path.name,
        "source_filename": source_path.name,
        "source_sha256": sha256_file(source_path),
        "sample_sha256": sha256_file(output_path),
        "window_col_offset": int(col_off),
        "window_row_offset": int(row_off),
        "width": SAMPLE_SIZE,
        "height": SAMPLE_SIZE,
        "center_longitude": lon,
        "center_latitude": lat,
        **provenance,
    }


def main() -> None:
    mars_image = settings.DATA_DIR / "raw" / "mars" / "MEGT44N000HB.IMG"
    mars_label = settings.DATA_DIR / "raw" / "mars" / "MEGT44N000HB.lbl"
    manifests = [json.loads(path.read_text()) for path in settings.manifests_dir.glob("*.json")]
    earth_manifest = next(
        (
            item
            for item in manifests
            if item.get("product_metadata", {}).get("product_id") == "COP-DEM-GLO30-18-77"
        ),
        None,
    )
    if earth_manifest is None:
        raise FileNotFoundError("Copernicus tile manifest was not found")
    earth = settings.DATA_DIR / "raw" / "earth" / f"{earth_manifest['id']}.tif"
    if not mars_image.is_file() or not mars_label.is_file() or not earth.is_file():
        raise FileNotFoundError(
            "Acquire and ingest the documented MOLA and Copernicus products first"
        )
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "description": "Compact samples are exact windows cut from acquired source rasters.",
        "samples": [
            write_sample(
                mars_image,
                mars_label,
                FIXTURE_DIR / "mola_megt44n000hb_jezero_window.tif",
                77.5,
                18.4,
                {
                    "provider": "NASA/JPL MOLA via NASA PDS Geosciences Node",
                    "product_id": "MGS-M-MOLA-5-MEGDR-L3-V1.0 / MEGT44N000HB",
                    "vertical_reference": (
                        "GMM3 Mars areoid degree/order 50; radial topography, meters"
                    ),
                    "source_url": "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/megt44n000hb.img",
                    "label_sha256": sha256_file(mars_label),
                },
            ),
            write_sample(
                earth,
                earth,
                FIXTURE_DIR / "copernicus_glo30_n18_e077_window.tif",
                77.5,
                18.5,
                {
                    "provider": "Copernicus Programme; public AWS mirror",
                    "product_id": "Copernicus DEM GLO-30 Public DSM, 2021 release",
                    "vertical_reference": "EGM2008 orthometric height, meters",
                    "source_url": "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N18_00_E077_00_DEM/Copernicus_DSM_COG_10_N18_00_E077_00_DEM.tif",
                    "surface_type": "DSM including structures and vegetation",
                },
            ),
        ],
    }
    (FIXTURE_DIR / "sample-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
