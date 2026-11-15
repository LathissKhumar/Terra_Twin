# Phase 2 completion report: planetary and Earth data ingestion

Date validated: 2026-11-14 UTC

## Result

Phase 2 acceptance passes for the initial Mars-to-Earth ingestion path. Two authentic products were acquired, read through Rasterio/GDAL, recorded in SHA-256 manifests and surfaced through the versioned dataset API. The Earth tile demonstrates ingestion only; TerraTwin has not performed analogue discovery or identified a candidate site.

## Acquired products

### Mars: MOLA MEGDR

- Product identifier: `MEGT44N000HB.IMG`; dataset `MGS-M-MOLA-5-MEGDR-L3-V1.0`, product version 2.0.
- Provider: NASA/JPL MOLA, NASA PDS Geosciences Node.
- PDS source: [MOLA MEGDR archive directory](https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/), [official detached label](https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/megt44n000hb.lbl), [product documentation](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html).
- Spatial coverage: 0–44°N, 0–90°E; includes the Jezero reference region near 18.4°N, 77.5°E. The global dataset is not downloaded. The adjacent `MEGT00N000HB` tile is 0–44°S and was explicitly rejected as the wrong hemisphere.
- Source format: PDS3 fixed-length image; 11,520 samples × 5,632 lines; signed 16-bit big-endian; meters. GDAL 3.12.2 reads it using the PDS driver and detached label.
- Horizontal reference: label-defined IAU2000 planetocentric simple cylindrical Mars CRS, Mars sphere radius 3,396,000 m. Rasterio reports 463 m projected pixel spacing. Label posting is 128 pixels/degree (0.0078125°).
- Vertical reference: radial topography relative to the GMM3 areoid, degree/order 50.
- NoData: PDS label does not declare a sentinel and documents interpolation for bins without observations. GDAL's PDS driver reports -32768; that value is recorded in the manifest. This product's interpolated cells are not interpreted as direct MOLA observations.
- File size: 129,761,280 bytes.
- Raster SHA-256: `14022166079edafc99650f354e5a634e6eb2c2ea544b444c01cd8ee55437df36`.
- Label SHA-256: `bc624a238ba6d71a770a09f959ead96f1c144970fae435b8ca5e26208b42eec5`.
- Manifest: `data/manifests/14022166079edafc99650f354e5a634e6eb2c2ea544b444c01cd8ee55437df36.json` (ignored by Git).

### Earth: Copernicus DEM GLO-30 Public DSM

- Product: Copernicus DEM GLO-30 Public, 2021 release; one 1° tile object `Copernicus_DSM_COG_10_N18_00_E077_00_DEM`.
- Provider: Copernicus Programme; public AWS distribution.
- Source object: [exact COG](https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N18_00_E077_00_DEM/Copernicus_DSM_COG_10_N18_00_E077_00_DEM.tif), [AWS product registry](https://registry.opendata.aws/copernicus-dem/), [official product specifications](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM), [public mirror format/key notes](https://copernicus-dem-30m.s3.amazonaws.com/readme.html).
- Tile origin: 18°N, 77°E (tile nominally 18–19°N, 77–78°E). This location is a data-ingestion example, not a selected Earth analogue.
- Format: Cloud Optimized GeoTIFF, read by GDAL's GTiff driver; 3,600 × 3,600 float32 samples.
- Horizontal reference: WGS84-G1150; Rasterio CRS `EPSG:4326`. Actual transform spacing is 0.0002777778° on both axes (1 arcsecond); this actual transform, not a nominal “30 m” label, is in the manifest. Stored bounds reflect the raster's pixel-point registration.
- Vertical reference: EGM2008 orthometric height, meters.
- Surface type and limitations: DSM containing the top-reflective surface, including vegetation and buildings. No NoData sentinel is declared in this COG; the manifest records `null`, and no missing cells are substituted with zero.
- File size: 39,715,598 bytes.
- SHA-256: `51587b0a9af347ff0bfe95b51ccd4d145ffdf0f74fdf18ce0213028f8041d989`.
- Manifest: `data/manifests/51587b0a9af347ff0bfe95b51ccd4d145ffdf0f74fdf18ce0213028f8041d989.json` (ignored by Git).
- Attribution recorded in the manifest follows the official Copernicus notice: “© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved”. See the [official licence and citation guidance](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM#).

SHA-256 values above were calculated from the acquired source bytes and match both the manifest IDs and content-addressed stored rasters. The MOLA PDS label's fixed-record declaration (5,632 × 23,040 bytes) was checked against the exact 129,761,280-byte image before acceptance. A separate downloader check fetched the Copernicus object with the Python HTTPS downloader, required the acquired SHA-256, and matched 39,715,598 bytes before deleting the temporary duplicate.

## Real-source automated test fixtures

Two committed 64 × 64 GeoTIFF windows are exact windows read from the source rasters, with no synthetic elevation values:

| Fixture | Source window | Parent raster SHA-256 | Fixture SHA-256 |
|---|---:|---|---|
| `backend/tests/fixtures/data/mola_megt44n000hb_jezero_window.tif` | row 3245, column 9887; centered at 77.5°E, 18.4°N | `14022166079edafc99650f354e5a634e6eb2c2ea544b444c01cd8ee55437df36` | `859fd371928a2a20b26005e6daa1f092ef0312c28186ea478f4b60af875cd06e` |
| `backend/tests/fixtures/data/copernicus_glo30_n18_e077_window.tif` | row 1768, column 1768; centered at 77.5°E, 18.5°N | `51587b0a9af347ff0bfe95b51ccd4d145ffdf0f74fdf18ce0213028f8041d989` | `0c7b5d20bbf200216a1c8df7b88a97ca6cf59c5989813c77e1ecf553a9eac752` |

`sample-provenance.json` records the product identifiers, source URLs, label checksum where relevant, sample window, units and vertical references. `backend/scripts/build_real_sample_fixtures.py` reproduces both windows from the acquired sources.

## Implemented ingestion behavior

- Product-aware MOLA and Copernicus tile acquisition, plus a common local-raster ingest path.
- LOLA, HiRISE DTM and SRTM/NASADEM availability and sources are documented. Their product-specific downloaders are deferred: LOLA still needs an exact regional bundle/interface choice; HiRISE needs a selected DTM label/product; NASADEM authentication and acquisition were not assumed. Local GeoTIFF ingestion accepts explicit source metadata; supported GDAL-readable HGT is also allowed.
- Manifest fields include source/product/version, URL, acquisition timestamp, raw checksum and size, CRS/bounds/dimensions/transform spacing, vertical units/reference, NoData, dtype, validation status, license/attribution and product-specific metadata.
- Raw inputs are never rewritten. Acquired rasters and manifests live under ignored `data/` storage; no large source raster is tracked by Git.
- HTTPS transfers enforce a byte limit, `Content-Length` completeness and optional expected SHA-256, use a temporary file and publish only complete data. An interrupted or shortened response leaves no published artifact.
- Local input paths are restricted to a staged basename under the configured per-body data directory. No CRS or vertical metadata is guessed.
- The public dataset catalog omits filesystem paths.

## Commands and observed validation

- `backend/.venv/bin/ruff format --check backend/app backend/tests backend/scripts` — 58 files already formatted.
- `backend/.venv/bin/ruff check backend/app backend/tests backend/scripts` — all checks passed.
- `backend/.venv/bin/mypy --strict backend/app` — no issues in 41 source files.
- `backend/.venv/bin/pytest backend/tests -q -ra` — 25 passed, 1 skipped. The skipped check is the optional live PostgreSQL/PostGIS integration test; this phase did not start a database container.
- `UV_CACHE_DIR=/tmp/terratwin-uv-cache uv lock --check --directory backend` — lock resolved with no changes.
- `docker compose config -q` — Compose configuration parses. Containers were not started as part of Phase 2.
- `curl -fsS -o /dev/null -w 'HTTP %{http_code}\\n' http://localhost:3001` — frontend returned HTTP 200 and remains available at `http://localhost:3001`.
- Started FastAPI with Uvicorn on port 8765 and requested `GET /api/v1/datasets`; it returned HTTP 200 and both real manifests. The response contained no filesystem paths.
- Opened both full source rasters with Rasterio/GDAL 3.12.2: MOLA PDS (1.5.2) and Copernicus GTiff. Recomputed full-file checksums and confirmed the MOLA source and stored hash copy are byte-identical.
- No dependencies, imports, API calls or generated data from other projects are part of this ingestion path.

## Limitations and acceptance

The configured MOLA product is a regional 128-pixel/degree grid with interpolated bins; it cannot resolve all rover-scale terrain processes and is not a substitute for higher-resolution HiRISE DTMs. Copernicus GLO-30 is a DSM, not a bare-earth DTM. MOLA and Earth vertical references differ and are explicitly preserved; no vertical combination or terrain comparison is performed in this phase. The single Earth tile is an ingestion proof only; it does not constrain the future search to that tile. No discovery ranking, analogue claim, or suitability score has been generated.

| Phase 2 acceptance item | Result |
|---|---|
| Real Mars elevation product ingested | Pass — MOLA `MEGT44N000HB` |
| Real Earth elevation product ingested | Pass — Copernicus GLO-30 tile 18N/77E |
| Both readable with Rasterio/GDAL | Pass |
| Metadata and checksums recorded | Pass |
| Invalid inputs rejected | Pass — missing CRS/NoData, non-finite samples, corrupt/unsupported raster, bad transfer/checksum and short transfer cases tested |
| Source bytes preserved | Pass — content-addressed copies match source SHA-256; fixture source files remain unchanged during tests |
| No fabricated elevation observations/results | Pass — synthetic rasters only exercise validation errors; committed numeric samples are copied from the two real rasters |

**Phase 2 is complete. Phase 3 has not started and requires explicit approval.**

## Independent audit addendum — subsequent HiRISE source

The original Phase 2 acceptance run above used MOLA. A later product-specific
ingestion extended Mars coverage with the official HiRISE Jezero DTM
`DTEEC_048842_1985_048908_1985_U01` (PDS IMG, 411,068,320 bytes; SHA-256
`9e723a990ef2694474bbc2486039098c885d09b938e70b903d60c15cbf704008`). It is
readable through the PDS/GDAL path and verified against its embedded PDS label.
The product has about 1.01 m nominal posting, metre elevations referenced to
Mars 2000 Datum, and a PDS special NoData value. Its effective resolution is
not documented and remains null in the manifest. The official product URL and
label details are in the independent audit report. The later ScaleBridge and
discovery acceptance run uses this HiRISE source; the original MOLA evidence
above remains historical and is not treated as the current best-supported
Jezero input.
