# Dataset ingestion API

All routes are mounted under `/api/v1`. Errors use the application's JSON error envelope; invalid rasters return 400, missing staged files return 404, and remote acquisition failures return 502. Request parameter validation errors return 422.

## `GET /datasets`

Returns adapter capability descriptions and validated manifests. The response never exposes local artifact paths. Dataset manifests identify content by SHA-256 and include source/product metadata.

## `POST /datasets/acquire/mola-jezero`

Downloads and ingests the official `MEGT44N000HB` MOLA PDS3 tile plus its label. This is the verified tile covering 0–44°N, 0–90°E. It is a synchronous operation using a worker thread; a later job API can replace this for long-running acquisitions.

## `POST /datasets/acquire/copernicus-glo30?latitude=18&longitude=77`

Downloads and ingests one public GLO-30 tile by integer south/west tile origin. Accepted bounds are latitude -90..89 and longitude -180..179. A missing tile or failed transfer is surfaced; no substitute dataset is selected.

## `POST /datasets/ingest-local`

Accepts these query parameters: `filename`, `target_body` (`earth`, `mars`, or `moon`), `vertical_units`, `vertical_reference`, `provider`, `product`, and `attribution`. `filename` must be a basename of a raster already staged directly under the configured `data/raw/{target_body}/` directory. Symlinks escaping that body directory and arbitrary filesystem paths are rejected. The API does not accept file uploads or infer vertical units/references.

The local product must be readable by Rasterio/GDAL and include a CRS, a valid geotransform, one elevation band, supported numeric values, and a finite NoData sentinel unless the adapter explicitly documents the absence of a sentinel. GeoTIFF, PDS IMG, JPEG2000 and SRTM HGT are accepted when supported by the installed GDAL drivers.
