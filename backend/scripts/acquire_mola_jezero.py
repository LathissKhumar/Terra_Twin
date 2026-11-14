"""Acquire and ingest the official MOLA MEGT44N000HB Jezero coverage tile."""

from app.core.config import settings
from app.services.dataset_service import ingest_mola

if __name__ == "__main__":
    manifest = ingest_mola(settings.DATA_DIR)
    print(manifest.model_dump_json(indent=2))
