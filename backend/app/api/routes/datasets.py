"""Dataset catalog, verified inspection, acquisition and safe GeoTIFF upload."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import anyio
from fastapi import APIRouter, Header, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.exceptions import DatasetNotFoundError, InvalidRasterError
from app.domain.schemas.datasets import DatasetManifest
from app.engines.data_ingestion.adapters import adapter_status
from app.engines.data_ingestion.ingestion import MAX_BYTES, sha256_file
from app.services.dataset_service import (
    ingest_copernicus,
    ingest_hirise_jezero,
    ingest_local,
    ingest_mola,
)

router = APIRouter(prefix="/datasets", tags=["Datasets"])
_UPLOAD_CHUNK_BYTES = 1024 * 1024


def _load_manifest(dataset_id: str) -> tuple[DatasetManifest, Path]:
    if len(dataset_id) != 64 or any(char not in "0123456789abcdef" for char in dataset_id):
        raise DatasetNotFoundError("Dataset was not found")
    paths = list(settings.manifests_dir.glob(f"{dataset_id}.json"))
    if len(paths) != 1:
        raise DatasetNotFoundError("Dataset manifest was not found")
    try:
        manifest = DatasetManifest.model_validate_json(paths[0].read_text())
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Dataset manifest is invalid") from exc
    if manifest.id != dataset_id:
        raise HTTPException(503, "Dataset manifest identity does not match its filename")
    raster_root = (settings.raw_data_dir / manifest.target_body).resolve()
    rasters = [
        path.resolve()
        for suffix in (".img", ".tif", ".tiff", ".jp2", ".hgt")
        for path in raster_root.glob(f"{dataset_id}{suffix}")
    ]
    rasters = [path for path in rasters if path.is_relative_to(raster_root) and path.is_file()]
    if len(rasters) != 1:
        raise HTTPException(503, "Immutable source raster is unavailable or ambiguous")
    if sha256_file(rasters[0]) != manifest.checksum_sha256:
        raise HTTPException(503, "Source raster checksum does not match the manifest")
    return manifest, rasters[0]


@router.get("")
def list_datasets(
    target_body: Literal["mars", "moon", "earth"] | None = None,
) -> dict[str, Any]:
    datasets: list[dict[str, Any]] = []
    for path in sorted(settings.manifests_dir.glob("*.json")):
        try:
            manifest = DatasetManifest.model_validate_json(path.read_text())
        except (OSError, ValueError):
            continue
        if target_body is not None and manifest.target_body != target_body:
            continue
        try:
            _, raster = _load_manifest(manifest.id)
            available = True
            checksum_verified = True
            raster_bytes = raster.stat().st_size
        except (DatasetNotFoundError, HTTPException, OSError):
            available = False
            checksum_verified = False
            raster_bytes = None
        datasets.append(
            {
                "manifest": manifest.model_dump(mode="json"),
                "available": available,
                "checksum_verified": checksum_verified,
                "raster_size_bytes": raster_bytes,
            }
        )
    return {
        "adapters": adapter_status(),
        "datasets": datasets,
        "storage_limit_bytes": MAX_BYTES,
    }


@router.get("/{dataset_id}", response_model=DatasetManifest)
def inspect_dataset(dataset_id: str) -> DatasetManifest:
    manifest, _ = _load_manifest(dataset_id)
    return manifest


@router.post("/upload", response_model=DatasetManifest, status_code=201)
async def upload_geotiff(
    request: Request,
    filename: str = Header(min_length=1, max_length=200, alias="X-Filename"),
    target_body: Literal["mars", "moon", "earth"] = Query(),
    vertical_units: str = Query(min_length=1, max_length=20),
    vertical_reference: str = Query(min_length=1, max_length=200),
    provider: str = Query(min_length=1, max_length=200),
    product: str = Query(min_length=1, max_length=200),
    attribution: str = Query(min_length=1, max_length=500),
) -> DatasetManifest:
    """Stream one untrusted GeoTIFF into private staging, validate, then ingest."""
    safe_name = Path(filename).name
    suffix = Path(safe_name).suffix.lower()
    if safe_name != filename or suffix not in {".tif", ".tiff"}:
        raise HTTPException(415, "Upload a GeoTIFF with a plain .tif or .tiff filename")
    content_length = request.headers.get("content-length")
    if content_length and (not content_length.isdigit() or int(content_length) > MAX_BYTES):
        raise HTTPException(413, "GeoTIFF exceeds the configured upload size limit")
    staging = (settings.DATA_DIR / ".staging").resolve()
    staging.mkdir(parents=True, exist_ok=True)
    temporary = (staging / f"{uuid4().hex}{suffix}").resolve()
    if not temporary.is_relative_to(staging):
        raise HTTPException(400, "Upload staging target is invalid")
    total = 0
    try:
        async with await anyio.open_file(temporary, "wb") as output:
            async for chunk in request.stream():
                total += len(chunk)
                if total > MAX_BYTES:
                    raise HTTPException(413, "GeoTIFF exceeds the configured upload size limit")
                await output.write(chunk)
        if total == 0:
            raise HTTPException(400, "Uploaded GeoTIFF is empty")
        manifest = await run_in_threadpool(
            ingest_local,
            temporary,
            settings.DATA_DIR,
            target_body,
            vertical_units,
            vertical_reference,
            provider,
            product,
            attribution,
        )
        return manifest
    finally:
        temporary.unlink(missing_ok=True)


@router.post("/acquire/mola-jezero", response_model=DatasetManifest)
async def acquire_mola_route() -> DatasetManifest:
    try:
        return await run_in_threadpool(ingest_mola, settings.DATA_DIR)
    except (InvalidRasterError, DatasetNotFoundError):
        raise
    except Exception as exc:
        raise HTTPException(502, "MOLA acquisition failed; no substitute dataset was used") from exc


@router.post("/acquire/hirise-jezero", response_model=DatasetManifest)
async def acquire_hirise_jezero_route() -> DatasetManifest:
    """Acquire and register the official HiRISE DTM for the Jezero reference region."""
    try:
        return await run_in_threadpool(ingest_hirise_jezero, settings.DATA_DIR)
    except (InvalidRasterError, DatasetNotFoundError):
        raise
    except Exception as exc:
        raise HTTPException(
            502, "HiRISE DTM acquisition failed; no substitute dataset was used"
        ) from exc


@router.api_route("/provision", methods=["GET", "POST"])
async def provision_production_datasets() -> dict[str, Any]:
    """Execute dataset setup: download missing planetary & Earth rasters and verify checksums."""
    try:
        from scripts.ensure_production_rasters import run_provisioning

        result = await run_in_threadpool(run_provisioning, settings.DATA_DIR)
        return result
    except Exception as exc:
        raise HTTPException(500, f"Production dataset provisioning failed: {exc}") from exc


@router.post("/acquire/copernicus-glo30", response_model=DatasetManifest)
async def acquire_copernicus_route(
    latitude: int = Query(ge=-90, le=89),
    longitude: int = Query(ge=-180, le=179),
) -> DatasetManifest:
    try:
        return await run_in_threadpool(ingest_copernicus, latitude, longitude, settings.DATA_DIR)
    except (InvalidRasterError, DatasetNotFoundError):
        raise
    except Exception as exc:
        raise HTTPException(
            502, "Copernicus acquisition failed; no substitute dataset was used"
        ) from exc
