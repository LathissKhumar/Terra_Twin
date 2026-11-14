"""Product-specific, explicit acquisition definitions."""

from pathlib import Path

from app.core.exceptions import InvalidRasterError
from app.engines.data_ingestion.ingestion import download_to_path

MOLA_BASE = "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128"


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
        "HiRISE_DTM": "PDS IMG DTM; must supply explicit product label and metadata",
        "SRTM_NASADEM": "NASADEM HGT requires Earthdata; local GeoTIFF ingestion supported",
        "Copernicus_DEM": "GLO-30 public COG single-degree acquisition implemented",
    }
