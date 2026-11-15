"""Acquire the official MOLA MEGC44N000HB per-bin observation-count product."""

from app.core.config import settings
from app.services.dataset_service import ingest_mola, ingest_mola_observation_counts

if __name__ == "__main__":
    elevation_manifest = ingest_mola(settings.DATA_DIR)
    raster, label, manifest = ingest_mola_observation_counts(settings.DATA_DIR, elevation_manifest)
    print(manifest.model_dump_json(indent=2))
    print(f"Raster: {raster}")
    print(f"PDS label: {label}")
