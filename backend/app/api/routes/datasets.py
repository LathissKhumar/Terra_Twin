"""Dataset catalog, inspection, and explicit acquisition endpoints."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.domain.schemas.datasets import DatasetManifest
from app.engines.data_ingestion.adapters import adapter_status
from app.services.dataset_service import ingest_copernicus, ingest_local, ingest_mola

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.get("")
async def list_datasets() -> dict[str, object]:
    manifests = [
        DatasetManifest.model_validate_json(p.read_text()).model_dump(mode="json")
        for p in settings.manifests_dir.glob("*.json")
    ]
    return {"adapters": adapter_status(), "datasets": manifests}


@router.post("/ingest-local", response_model=DatasetManifest)
async def ingest_local_raster(
    filename: str,
    target_body: Literal["mars", "moon", "earth"],
    vertical_units: str,
    vertical_reference: str,
    provider: str,
    product: str,
    attribution: str,
) -> DatasetManifest:
    if Path(filename).name != filename or filename in {".", ".."}:
        raise HTTPException(400, "Supply a staged filename; paths are not accepted")
    # Input is a staged basename under raw/<body>, never a client filesystem path.
    source_root = (settings.raw_data_dir / target_body).resolve()
    source = (source_root / filename).resolve()
    if source_root not in source.parents or not source.is_file():
        raise HTTPException(404, "Staged raster file was not found")
    return ingest_local(
        source,
        settings.DATA_DIR,
        target_body,
        vertical_units,
        vertical_reference,
        provider,
        product,
        attribution,
    )


@router.post("/acquire/mola-jezero", response_model=DatasetManifest)
async def acquire_mola() -> DatasetManifest:
    return await run_in_threadpool(ingest_mola, settings.DATA_DIR)


@router.post("/acquire/copernicus-glo30", response_model=DatasetManifest)
async def acquire_copernicus(
    latitude: int = Query(ge=-90, le=89),
    longitude: int = Query(ge=-180, le=179),
) -> DatasetManifest:
    return await run_in_threadpool(ingest_copernicus, latitude, longitude, settings.DATA_DIR)
