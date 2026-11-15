"""Dataset ingest orchestration."""

import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import rasterio

from app.core.exceptions import DatasetNotFoundError, InvalidRasterError
from app.domain.schemas.datasets import DatasetManifest
from app.domain.schemas.observation_counts import ObservationCountsManifest
from app.engines.data_ingestion.adapters import (
    HIRISE_JEZERO_BYTES,
    HIRISE_JEZERO_PRODUCT_ID,
    HIRISE_JEZERO_URL,
    acquire_copernicus_glo30,
    acquire_hirise_jezero,
    acquire_jezero_mola,
    acquire_jezero_mola_counts,
    copernicus_glo30_url,
    validate_hirise_jezero,
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


def ingest_hirise_jezero(data_dir: Path) -> DatasetManifest:
    """Register the real 1 m class HiRISE stereo DTM with embedded PDS labels."""
    existing = _existing_manifest(data_dir, HIRISE_JEZERO_PRODUCT_ID)
    if existing:
        return existing
    raster = acquire_hirise_jezero(data_dir)
    validate_hirise_jezero(raster)
    return ingest_file(
        raster,
        data_dir=data_dir,
        target_body="mars",
        provider="University of Arizona HiRISE / NASA PDS",
        product="HiRISE stereo-derived Jezero DTM",
        version="DTEEC_048842_1985_048908_1985_U01",
        source_url=HIRISE_JEZERO_URL,
        vertical_units="m",
        vertical_reference="Mars 2000 Datum (areoid)",
        resolution_unit="m",
        attribution="NASA/JPL/University of Arizona; HiRISE public data product",
        license="Publicly available HiRISE data; cite the product and source observations",
        product_metadata={
            "product_id": HIRISE_JEZERO_PRODUCT_ID,
            "source_observation_ids": "ESP_048842_1985,ESP_048908_1985",
            "nominal_ground_sample_distance_m": 1.0096633268711,
            "effective_resolution_m": None,
            "vertical_datum": "Mars 2000 Datum",
            "coordinate_system": "Mars Equirectangular, planetocentric",
            "sample_format": "PDS3 PC_REAL 32-bit floating point",
            "nodata_convention": (
                "PDS special constant 16#FF7FFFFB#; GDAL PDS driver maps to float32 minimum"
            ),
            "source_product_bytes": HIRISE_JEZERO_BYTES,
            "label_convention": "PDS label embedded in the IMG file",
            "geographic_coverage": "18.336842565755–18.588602118832 N, 77.46147725–77.58415512 E",
            "center_latitude_planetocentric_deg": 15.0,
            "center_longitude_east_deg": 77.52,
        },
        allow_missing_nodata=False,
    )


def ingest_mola_observation_counts(
    data_dir: Path, topography: DatasetManifest
) -> tuple[Path, Path, ObservationCountsManifest]:
    """Acquire and register MOLA counts ancillary to the exact ingested topography."""
    if (
        topography.target_body != "mars"
        or topography.product_metadata.get("product_id") != "MEGT44N000HB"
    ):
        raise InvalidRasterError("MOLA observation counts require the MEGT44N000HB topography")
    source, label = acquire_jezero_mola_counts(data_dir)
    digest = sha256_file(source)
    label_digest = sha256_file(label)
    try:
        with rasterio.open(label) as dataset:
            if (
                dataset.count != 1
                or dataset.dtypes[0] != "uint8"
                or dataset.width != topography.width
                or dataset.height != topography.height
                or dataset.crs is None
            ):
                raise InvalidRasterError("MOLA counts raster does not match the topography grid")
            bounds = (
                dataset.bounds.left,
                dataset.bounds.bottom,
                dataset.bounds.right,
                dataset.bounds.top,
            )
            with rasterio.open(
                data_dir / "raw" / "mars" / str(topography.product_metadata["tile_label"])
            ) as dem:
                if dataset.transform != dem.transform or not dataset.crs == dem.crs:
                    raise InvalidRasterError(
                        "MOLA counts and elevation grids are not co-registered"
                    )
            observed = 0
            maximum = 0
            for _, window in dataset.block_windows(1):
                counts = dataset.read(1, window=window)
                observed += int(np.count_nonzero(counts))
                maximum = max(maximum, int(counts.max(initial=0)))
            if dataset.width * dataset.height != 5632 * 11520:
                raise InvalidRasterError(
                    "MOLA counts dimensions differ from the official tile label"
                )
            manifest = ObservationCountsManifest(
                id=digest,
                checksum_sha256=digest,
                source_topography_id=topography.id,
                provider="NASA PDS Geosciences Node",
                product="MGS MOLA MEGDR observations per bin",
                product_id="MEGC44N000HB",
                source_url=(
                    "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/"
                    "mgsl_300x/meg128/megc44n000hb.img"
                ),
                label_source_url=(
                    "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/"
                    "mgsl_300x/meg128/megc44n000hb.lbl"
                ),
                downloaded_at=datetime.now(UTC),
                file_size_bytes=source.stat().st_size,
                crs=dataset.crs.to_string(),
                bounds=bounds,
                width=dataset.width,
                height=dataset.height,
                pixel_resolution_x=abs(dataset.res[0]),
                pixel_resolution_y=abs(dataset.res[1]),
                dtype=dataset.dtypes[0],
                count_units="MOLA observations per 0.0078125-degree MEGDR bin",
                zero_count_means_unobserved=True,
                total_cells=dataset.width * dataset.height,
                observed_cells=observed,
                maximum_count=maximum,
                label_checksum_sha256=label_digest,
                attribution="NASA/JPL/MOLA; PDS Geosciences Node",
            )
    except (OSError, rasterio.errors.RasterioError) as exc:
        if isinstance(exc, InvalidRasterError):
            raise
        raise InvalidRasterError("Could not inspect the MOLA observation-count raster") from exc

    raw_dir = data_dir / "raw" / "mars"
    stored_raster = raw_dir / f"{digest}.img"
    if stored_raster.exists():
        if sha256_file(stored_raster) != digest:
            raise InvalidRasterError("Existing MOLA count artifact checksum mismatch")
    else:
        with (
            source.open("rb") as input_stream,
            tempfile.NamedTemporaryFile(dir=raw_dir, delete=False) as temporary,
        ):
            temp_path = Path(temporary.name)
            shutil.copyfileobj(input_stream, temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
        try:
            os.link(temp_path, stored_raster)
        except FileExistsError:
            if sha256_file(stored_raster) != digest:
                raise InvalidRasterError(
                    "Concurrent MOLA count ingestion checksum mismatch"
                ) from None
        except OSError:
            raise
        finally:
            temp_path.unlink(missing_ok=True)
    ancillary_dir = data_dir / "manifests" / "ancillary"
    ancillary_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = ancillary_dir / f"{digest}.json"
    if manifest_path.exists():
        prior = ObservationCountsManifest.model_validate_json(manifest_path.read_text())
        if prior.source_topography_id != topography.id:
            raise InvalidRasterError("Existing count provenance is linked to another DEM")
        manifest = prior
    else:
        manifest_path.write_text(manifest.model_dump_json(indent=2))
    return stored_raster, label, manifest


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
