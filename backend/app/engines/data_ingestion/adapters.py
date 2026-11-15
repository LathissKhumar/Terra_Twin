"""Product-specific, explicit acquisition definitions."""

import math
import re
from pathlib import Path

import rasterio
from pyproj import CRS

from app.core.exceptions import InvalidRasterError
from app.engines.data_ingestion.ingestion import download_to_path

MOLA_BASE = "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128"
MOLA_COUNTS_PRODUCT_ID = "MEGC44N000HB"
HIRISE_JEZERO_PRODUCT_ID = "DTEEC_048842_1985_048908_1985_U01"
HIRISE_JEZERO_URL = (
    "https://www.uahirise.org/PDS/DTM/ESP/ORB_048800_048899/"
    "ESP_048842_1985_ESP_048908_1985/"
    f"{HIRISE_JEZERO_PRODUCT_ID}.IMG"
)
HIRISE_JEZERO_BYTES = 411_068_320


def acquire_hirise_jezero(data_dir: Path) -> Path:
    """Acquire the official embedded-label HiRISE DTM covering Jezero."""
    root = data_dir / "raw" / "mars"
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"{HIRISE_JEZERO_PRODUCT_ID}.IMG"
    if destination.exists():
        if destination.stat().st_size != HIRISE_JEZERO_BYTES:
            raise InvalidRasterError("Existing HiRISE DTM size differs from the official product")
        return destination
    return download_to_path(HIRISE_JEZERO_URL, destination, max_bytes=HIRISE_JEZERO_BYTES)


def validate_hirise_jezero(path: Path) -> None:
    """Check the attached PDS label and grid against the selected official DTM."""
    if not path.is_file() or path.stat().st_size != HIRISE_JEZERO_BYTES:
        raise InvalidRasterError("HiRISE file size differs from the selected PDS product")
    try:
        with rasterio.open(path) as dataset:
            tags = dataset.tags()
            product_id = tags.get("PRODUCT_ID", "").strip('"')
            crs = CRS.from_wkt(dataset.crs.to_wkt()) if dataset.crs else None
            nodata_is_pds_float_minimum = dataset.nodata is not None and math.isclose(
                dataset.nodata, -3.4028234663852886e38, rel_tol=1e-6
            )
            valid = (
                product_id == HIRISE_JEZERO_PRODUCT_ID
                and dataset.driver == "PDS"
                and dataset.width == 6955
                and dataset.height == 14775
                and dataset.count == 1
                and dataset.dtypes == ("float32",)
                and crs is not None
                and crs.geodetic_crs is not None
                and "MARS" in crs.geodetic_crs.name.upper()
                and crs.coordinate_operation is not None
                and any(
                    term in crs.coordinate_operation.method_name.casefold()
                    for term in ("equirectangular", "equidistant cylindrical")
                )
                and nodata_is_pds_float_minimum
                and math.isclose(dataset.res[0], 1.0096633268711, rel_tol=1e-8)
                and math.isclose(dataset.res[1], 1.0096633268711, rel_tol=1e-8)
            )
            if not valid:
                raise InvalidRasterError(
                    "HiRISE embedded PDS label or grid does not match the selected Jezero DTM"
                )
    except InvalidRasterError:
        raise
    except Exception as exc:
        raise InvalidRasterError(
            "Could not validate the HiRISE PDS image and attached label"
        ) from exc


def acquire_jezero_mola(data_dir: Path) -> tuple[Path, Path]:
    """Download only the 90x44 degree MOLA MEGDR tile and detached PDS label."""
    root = data_dir / "raw" / "mars"
    # The 44N tile spans 0–44°N; the similarly named 00N tile is the
    # southern tile (0–44°S) according to its PDS label.
    stem = "megt44n000hb"
    root.mkdir(parents=True, exist_ok=True)
    label = root / f"{stem.upper()}.lbl"
    if not label.exists():
        download_to_path(f"{MOLA_BASE}/{stem}.lbl", label, max_bytes=100_000)
    label_text = label.read_text(encoding="ascii")
    label_fields = {
        key.strip(): value.strip()
        for line in label_text.splitlines()
        if "=" in line
        for key, _, value in [line.partition("=")]
    }
    try:
        expected_bytes = int(label_fields["FILE_RECORDS"]) * int(label_fields["RECORD_BYTES"])
    except (KeyError, ValueError) as exc:
        raise InvalidRasterError("MOLA PDS label lacks a valid fixed-record byte count") from exc
    required = {
        "PRODUCT_ID": '"MEGT44N000HB.IMG"',
        "MAXIMUM_LATITUDE": "44.0 <DEGREE>",
        "MINIMUM_LATITUDE": "0.0 <DEGREE>",
        "WESTERNMOST_LONGITUDE": "0.0 <DEGREE>",
        "EASTERNMOST_LONGITUDE": "90.0 <DEGREE>",
    }
    for key, expected in required.items():
        if label_fields.get(key) != expected:
            raise InvalidRasterError("MOLA label does not describe the Jezero coverage tile")
    raster = root / f"{stem.upper()}.IMG"
    if raster.exists():
        if raster.stat().st_size != expected_bytes:
            raise InvalidRasterError("Existing MOLA image is incomplete relative to its PDS label")
    else:
        download_to_path(f"{MOLA_BASE}/{stem}.img", raster, max_bytes=150_000_000)
        if raster.stat().st_size != expected_bytes:
            raster.unlink(missing_ok=True)
            raise InvalidRasterError("Downloaded MOLA image size does not match its PDS label")
    return raster, label


def parse_jezero_mola_counts_label(label_text: str) -> int:
    """Validate the official co-registered MOLA count tile label and return bytes."""
    fields = {
        key.upper(): value.strip().strip('"')
        for key, value in re.findall(r"^\s*([A-Z_]+)\s*=\s*(.*?)\s*$", label_text, re.M)
    }
    required = {
        "PRODUCT_ID": "MEGC44N000HB.IMG",
        "RECORD_BYTES": "11520",
        "FILE_RECORDS": "5632",
        "LINES": "5632",
        "LINE_SAMPLES": "11520",
        "SAMPLE_TYPE": "UNSIGNED_INTEGER",
        "SAMPLE_BITS": "8",
        "MAP_RESOLUTION": "128.0 <PIXEL/DEGREE>",
        "MAXIMUM_LATITUDE": "44.0 <DEGREE>",
        "MINIMUM_LATITUDE": "0.0 <DEGREE>",
        "WESTERNMOST_LONGITUDE": "0.0 <DEGREE>",
        "EASTERNMOST_LONGITUDE": "90.0 <DEGREE>",
    }
    for key, expected in required.items():
        if fields.get(key) != expected:
            raise InvalidRasterError(
                "MOLA counts label does not match the Jezero tile specification"
            )
    return int(fields["FILE_RECORDS"]) * int(fields["RECORD_BYTES"])


def acquire_jezero_mola_counts(data_dir: Path) -> tuple[Path, Path]:
    """Acquire the official 8-bit counts tile aligned with MEGT44N000HB."""
    root = data_dir / "raw" / "mars"
    stem = MOLA_COUNTS_PRODUCT_ID.lower()
    root.mkdir(parents=True, exist_ok=True)
    label = root / f"{MOLA_COUNTS_PRODUCT_ID}.lbl"
    if not label.exists():
        download_to_path(f"{MOLA_BASE}/{stem}.lbl", label, max_bytes=100_000)
    expected_bytes = parse_jezero_mola_counts_label(label.read_text(encoding="ascii"))
    raster = root / f"{MOLA_COUNTS_PRODUCT_ID}.IMG"
    if raster.exists():
        if raster.stat().st_size != expected_bytes:
            raise InvalidRasterError("Existing MOLA counts image size differs from its PDS label")
    else:
        download_to_path(f"{MOLA_BASE}/{stem}.img", raster, max_bytes=expected_bytes)
        if raster.stat().st_size != expected_bytes:
            raster.unlink(missing_ok=True)
            raise InvalidRasterError("MOLA counts image size differs from its PDS label")
    return raster, label


def copernicus_glo30_url(latitude: int, longitude: int) -> str:
    """Return official public COG key URL for one 1-degree tile."""
    if not -90 <= latitude <= 89 or not -180 <= longitude <= 179:
        raise ValueError("Tile origin must identify an Earth 1-degree tile")
    ns = "N" if latitude >= 0 else "S"
    ew = "E" if longitude >= 0 else "W"
    tile = f"Copernicus_DSM_COG_10_{ns}{abs(latitude):02d}_00_{ew}{abs(longitude):03d}_00_DEM"
    return f"https://copernicus-dem-30m.s3.amazonaws.com/{tile}/{tile}.tif"


def acquire_copernicus_glo30(latitude: int, longitude: int, data_dir: Path) -> Path:
    url = copernicus_glo30_url(latitude, longitude)
    tile = url.rsplit("/", 1)[-1]
    destination = data_dir / "raw" / "earth" / tile
    if destination.exists():
        if not 0 < destination.stat().st_size <= 100_000_000:
            raise InvalidRasterError("Existing Copernicus object has an invalid file size")
        return destination
    return download_to_path(url, destination, max_bytes=100_000_000)


def adapter_status() -> dict[str, str]:
    return {
        "MOLA": "MEGDR 128 px/degree tiled PDS IMG; Jezero tile downloader implemented",
        "LOLA": "LOLA_GDR PDS4 gridded DEM; product downloader deferred",
        "HiRISE_DTM": "DTEEC_048842_1985_048908_1985_U01 Jezero PDS IMG acquisition implemented",
        "SRTM_NASADEM": (
            "Local HGT/GeoTIFF ingestion supported; "
            "product-specific authenticated downloader deferred"
        ),
        "Copernicus_DEM": "GLO-30 public COG single-degree acquisition implemented",
    }
