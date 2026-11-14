"""Dataset ingest orchestration."""

import json
from pathlib import Path

from app.core.exceptions import DatasetNotFoundError, InvalidRasterError
from app.domain.schemas.datasets import DatasetManifest
from app.engines.data_ingestion.adapters import (
    acquire_copernicus_glo30,
    acquire_jezero_mola,
    copernicus_glo30_url,
)
from app.engines.data_ingestion.ingestion import Body, ingest_file, sha256_file


def _existing_manifest(data_dir: Path, product_id: str) -> DatasetManifest | None:
    manifests_dir = data_dir / "manifests"
    for manifest_path in manifests_dir.glob("*.json"):
        data = json.loads(manifest_path.read_text())
        if data.get("product_metadata", {}).get("product_id") == product_id:
            manifest = DatasetManifest.model_validate(data)
            # MOLA and GeoTIFF object IDs are unique; check standard suffixes rather
            # than taking an arbitrary filename from a request.
            candidates = (
                data_dir / "raw" / manifest.target_body / f"{manifest.id}.img",
                data_dir / "raw" / manifest.target_body / f"{manifest.id}.tif",
                data_dir / "raw" / manifest.target_body / f"{manifest.id}.tiff",
            )
            if any(path.is_file() for path in candidates):
                return manifest
            raise DatasetNotFoundError("Dataset manifest exists but its raster artifact is missing")
    return None


def ingest_local(
    path: Path,
    data_dir: Path,
    body: Body,
    vertical_units: str,
    vertical_reference: str,
    provider: str,
    product: str,
    attribution: str,
) -> DatasetManifest:
    if body == "mars" and (vertical_reference == "unknown" or not vertical_reference):
        raise InvalidRasterError("Planetary vertical reference must be stated")
    return ingest_file(
        path,
        data_dir=data_dir,
        target_body=body,
        provider=provider,
        product=product,
        vertical_units=vertical_units,
        vertical_reference=vertical_reference,
        attribution=attribution,
    )


def ingest_mola(data_dir: Path) -> DatasetManifest:
    existing = _existing_manifest(data_dir, "MEGT44N000HB")
    if existing:
        return existing
    raster, label = acquire_jezero_mola(data_dir)
    result = ingest_file(
        raster,
        data_dir=data_dir,
        target_body="mars",
        provider="NASA PDS Geosciences Node",
        product="MGS MOLA MEGDR median topography",
        version="MGS-M-MOLA-5-MEGDR-L3-V1.0 / product 2.0",
        source_url="https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/megt44n000hb.img",
        vertical_units="m",
        vertical_reference="GMM3 Mars areoid, degree/order 50; radial topography",
        resolution_unit="m",
        attribution="NASA/JPL/MOLA; PDS Geosciences Node",
        product_metadata={
            "product_id": "MEGT44N000HB",
            "tile_label": label.name,
            "tile_label_sha256": sha256_file(label),
            "tile_label_size_bytes": label.stat().st_size,
            "nominal_resolution_pixels_per_degree": 128,
            "nominal_angular_pixel_spacing_degrees": 0.0078125,
            "nominal_equatorial_map_scale_km_per_pixel": 0.463,
            "tile_coverage": "0-44N, 0-90E",
            "coordinate_system": "IAU2000 planetocentric; simple cylindrical",
            "sample_type": "MSB signed integer, 16-bit",
            "nodata_convention": (
                "PDS label declares no sentinel; GDAL PDS driver reports -32768; "
                "bins without observations are interpolated"
            ),
            "source_label_url": "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/megt44n000hb.lbl",
        },
        allow_missing_nodata=True,
        raster_open_path=label,
    )
    return result


def ingest_copernicus(latitude: int, longitude: int, data_dir: Path) -> DatasetManifest:
    product_id = f"COP-DEM-GLO30-{latitude}-{longitude}"
    existing = _existing_manifest(data_dir, product_id)
    if existing:
        return existing
    path = acquire_copernicus_glo30(latitude, longitude, data_dir)
    result = ingest_file(
        path,
        data_dir=data_dir,
        target_body="earth",
        provider="Copernicus Programme (public AWS mirror)",
        product="Copernicus DEM GLO-30 Public DSM",
        version="2021 release",
        source_url=copernicus_glo30_url(latitude, longitude),
        vertical_units="m",
        vertical_reference="EGM2008 orthometric height",
        attribution=(
            "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 "
            "provided under COPERNICUS by the European Union and ESA; all rights reserved"
        ),
        resolution_unit="degrees",
        license="Copernicus DEM user license terms",
        product_metadata={
            "product_id": product_id,
            "tile_origin_latitude": latitude,
            "tile_origin_longitude": longitude,
            "surface_type": "DSM",
            "nodata_convention": "Source COG has no declared NoData sentinel",
        },
        allow_missing_nodata=True,
    )
    if path.resolve() != (data_dir / "raw" / "earth" / f"{result.id}.tif").resolve():
        path.unlink(missing_ok=True)
    return result
