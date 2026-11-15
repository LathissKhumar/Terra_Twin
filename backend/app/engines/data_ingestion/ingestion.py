"""Safe raster ingestion, checksums, immutable raw storage and provenance manifests."""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict

import numpy as np
import rasterio
from rasterio.errors import RasterioError

from app.core.exceptions import DatasetAcquisitionError, InvalidRasterError
from app.domain.schemas.datasets import DatasetManifest

Body = Literal["mars", "moon", "earth"]
MAX_BYTES = 2_000_000_000
ALLOWED_DTYPES = {"uint8", "int16", "uint16", "int32", "uint32", "float32", "float64"}
ALLOWED_VERTICAL_UNITS = {"m", "meter", "meters", "metre", "metres"}


class RasterDetails(TypedDict):
    crs: str
    bounds: tuple[float, float, float, float]
    width: int
    height: int
    pixel_resolution_x: float
    pixel_resolution_y: float
    nodata: float | int | None
    dtype: str
    media_type: str
    valid_pixels: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inspect_raster(
    path: Path,
    *,
    vertical_units: str,
    allow_missing_nodata: bool = False,
    open_path: Path | None = None,
) -> RasterDetails:
    if path.stat().st_size <= 0 or path.stat().st_size > MAX_BYTES:
        raise InvalidRasterError("Raster file size is invalid")
    if path.suffix.lower() not in {".tif", ".tiff", ".img", ".jp2", ".hgt"}:
        raise InvalidRasterError("Unsupported raster extension")
    if vertical_units.casefold() not in ALLOWED_VERTICAL_UNITS:
        raise InvalidRasterError("Vertical units must be explicitly identified as metres")
    try:
        with rasterio.open(open_path or path) as ds:
            if ds.count != 1 or ds.width < 2 or ds.height < 2:
                raise InvalidRasterError(
                    "Elevation raster must have one band and at least 2x2 cells"
                )
            if ds.crs is None:
                raise InvalidRasterError("Raster CRS is missing; CRS is never inferred")
            transform_values = tuple(ds.transform)
            if (
                not all(math.isfinite(value) for value in transform_values)
                or ds.transform.determinant == 0
            ):
                raise InvalidRasterError("Raster geotransform is invalid")
            if ds.dtypes[0] not in ALLOWED_DTYPES:
                raise InvalidRasterError("Raster data type is unsupported")
            if ds.nodata is None and not allow_missing_nodata:
                raise InvalidRasterError(
                    "NoData sentinel is missing and not documented for this product"
                )
            if ds.nodata is not None and not math.isfinite(float(ds.nodata)):
                raise InvalidRasterError("A finite NoData sentinel must be explicitly defined")
            valid = 0
            for _, window in ds.block_windows(1):
                band = ds.read(1, window=window)
                mask = ds.read_masks(1, window=window) > 0
                values = band[mask]
                if values.size:
                    if not bool(np.isfinite(values).all()):
                        raise InvalidRasterError("Raster contains non-finite valid elevations")
                    valid += int(values.size)
            if not valid:
                raise InvalidRasterError("Raster contains no valid elevation cells")
            resolution = ds.res
            bounds = (ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top)
            return {
                "crs": ds.crs.to_string(),
                "bounds": bounds,
                "width": ds.width,
                "height": ds.height,
                "pixel_resolution_x": abs(resolution[0]),
                "pixel_resolution_y": abs(resolution[1]),
                "nodata": ds.nodata,
                "dtype": ds.dtypes[0],
                "media_type": ds.driver,
                "valid_pixels": valid,
            }
    except (RasterioError, OSError, ValueError) as exc:
        if isinstance(exc, InvalidRasterError):
            raise
        raise InvalidRasterError("Raster could not be opened or read") from exc


def ingest_file(
    source: Path,
    *,
    data_dir: Path,
    target_body: Body,
    provider: str,
    product: str,
    vertical_units: str,
    vertical_reference: str,
    source_url: str | None = None,
    version: str | None = None,
    license: str | None = None,
    attribution: str,
    resolution_unit: str = "source CRS units",
    product_metadata: dict[str, str | int | float | None] | None = None,
    allow_missing_nodata: bool = False,
    raster_open_path: Path | None = None,
) -> DatasetManifest:
    source = source.resolve(strict=True)
    details = _inspect_raster(
        source,
        vertical_units=vertical_units,
        allow_missing_nodata=allow_missing_nodata,
        open_path=raster_open_path,
    )
    digest = sha256_file(source)
    folder = data_dir / "raw" / target_body
    manifests = data_dir / "manifests"
    folder.mkdir(parents=True, exist_ok=True)
    manifests.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{digest}{source.suffix.lower()}"
    manifest_path = manifests / f"{digest}.json"
    if dest.exists():
        if sha256_file(dest) != digest:
            raise InvalidRasterError("Existing raw artifact checksum mismatch")
        if manifest_path.exists():
            return DatasetManifest.model_validate_json(manifest_path.read_text())
    else:
        # Atomic copy; do not overwrite existing raw source artifacts.
        with tempfile.NamedTemporaryFile(dir=folder, delete=False) as tmp:
            temp_path = Path(tmp.name)
            with source.open("rb") as inp:
                shutil.copyfileobj(inp, tmp)
            tmp.flush()
            os.fsync(tmp.fileno())
        try:
            os.link(temp_path, dest)
        except FileExistsError:
            if sha256_file(dest) != digest:
                raise InvalidRasterError(
                    "Concurrent ingestion produced checksum mismatch"
                ) from None
        finally:
            temp_path.unlink(missing_ok=True)
    manifest = DatasetManifest(
        id=digest,
        target_body=target_body,
        provider=provider,
        product=product,
        version=version,
        source_url=source_url,
        downloaded_at=datetime.now(UTC),
        checksum_sha256=digest,
        file_size_bytes=dest.stat().st_size,
        crs=details["crs"],
        bounds=details["bounds"],
        width=details["width"],
        height=details["height"],
        pixel_resolution_x=details["pixel_resolution_x"],
        pixel_resolution_y=details["pixel_resolution_y"],
        resolution_unit=resolution_unit,
        vertical_units=vertical_units,
        vertical_reference=vertical_reference,
        nodata=details["nodata"],
        dtype=details["dtype"],
        processing_status="validated",
        license=license,
        attribution=attribution,
        media_type=details["media_type"],
        product_metadata={**(product_metadata or {}), "valid_pixel_count": details["valid_pixels"]},
    )
    # Atomic manifest; if provenance writing fails, remove only this new raw copy.
    tmp_manifest = manifest_path.with_suffix(".json.tmp")
    try:
        tmp_manifest.write_text(manifest.model_dump_json(indent=2))
        os.replace(tmp_manifest, manifest_path)
    except OSError:
        tmp_manifest.unlink(missing_ok=True)
        if dest.exists() and sha256_file(dest) == digest:
            dest.unlink()
        raise
    return manifest


def download_to_path(
    url: str, destination: Path, *, expected_sha256: str | None = None, max_bytes: int = MAX_BYTES
) -> Path:
    """Stream to a temporary file and publish only complete, checksum-verified bytes."""
    if not url.startswith("https://"):
        raise ValueError("Only HTTPS downloads are accepted")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError("Download destination already exists")
    request = urllib.request.Request(url, headers={"User-Agent": "TerraTwin/0.1"})
    temp_path: Path | None = None
    try:
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                length = response.headers.get("Content-Length")
                try:
                    expected_length = int(length) if length is not None else None
                except ValueError as exc:
                    raise DatasetAcquisitionError(
                        "Remote response has an invalid Content-Length"
                    ) from exc
                if expected_length is not None and expected_length > max_bytes:
                    raise DatasetAcquisitionError("Remote file exceeds configured size limit")
                digest = hashlib.sha256()
                total = 0
                with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as tmp:
                    temp_path = Path(tmp.name)
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > max_bytes:
                            raise DatasetAcquisitionError(
                                "Remote file exceeds configured size limit"
                            )
                        digest.update(chunk)
                        tmp.write(chunk)
                    tmp.flush()
                    os.fsync(tmp.fileno())
            if expected_length is not None and total != expected_length:
                raise DatasetAcquisitionError(
                    "Remote dataset transfer ended before Content-Length bytes arrived"
                )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DatasetAcquisitionError("Remote dataset download failed") from exc
        if not total:
            raise DatasetAcquisitionError("Remote file is empty")
        if expected_sha256 and digest.hexdigest() != expected_sha256.lower():
            raise DatasetAcquisitionError(
                "Downloaded file checksum does not match expected SHA-256"
            )
        os.link(temp_path, destination)
        return destination
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)
