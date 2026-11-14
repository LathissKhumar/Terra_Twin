"""Acquire and ingest one integer-degree Copernicus GLO-30 tile."""

import argparse

from app.core.config import settings
from app.services.dataset_service import ingest_copernicus


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("latitude", type=int, help="Integer south edge of tile, -90..89")
    parser.add_argument("longitude", type=int, help="Integer west edge of tile, -180..179")
    args = parser.parse_args()
    manifest = ingest_copernicus(args.latitude, args.longitude, settings.DATA_DIR)
    print(manifest.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
