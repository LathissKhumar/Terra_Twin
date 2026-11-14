# Phase 2: dataset acquisition and ingestion

## Supported data and current adapter scope

| Adapter | Dataset/product | Phase 2 capability |
|---|---|---|
| MOLA | MGS MOLA MEGDR L3, `MGS-M-MOLA-5-MEGDR-L3-V1.0` | Downloads the 0–44°N, 0–90°E `MEGT44N000HB` PDS3 tile and label. This tile contains Jezero (about 18.4°N, 77.5°E). |
| Copernicus | GLO-30 Public DSM, 2021 release | Downloads an individual public COG using the published AWS object-key convention. The 18°N, 77°E tile is used to demonstrate a real Earth ingestion, not claimed as an analogue discovery. |
| LOLA | LRO LOLA gridded products | Adapter is documented; automatic product discovery/download remains deferred pending selection of an exact regional product and archive interface. |
| HiRISE DTM | MRO HiRISE derived terrain models | Adapter is documented; user must provide a selected product and its PDS label. Product-level ingestion is not yet enabled. |
| SRTM/NASADEM | Earth elevation products | Local raster ingestion is supported. Earthdata-authenticated product downloads are deferred; no credentials or download behavior are assumed. |

No global MOLA product is downloaded. `MEGT00N000HB` is explicitly not the Jezero tile: its label says 0–44°S. The selected northern tile is `MEGT44N000HB`.

## Source specifications verified

### MOLA

The detached PDS3 label identifies `PRODUCT_ID=MEGT44N000HB.IMG`, dataset version `MGS-M-MOLA-5-MEGDR-L3-V1.0`, product version 2.0, 5,632 lines by 11,520 samples, signed 16-bit big-endian samples, and meters. The map is simple cylindrical, planetocentric, IAU2000, 128 pixels/degree (0.0078125° nominal angular posting), covering 0–44°N and 0–90°E. GDAL's PDS driver interprets the label and reports a Mars-centered simple cylindrical projected CRS with 463 m pixel spacing. Heights are radial topography relative to the GMM3 areoid (degree/order 50). The label declares no NoData sentinel; its description says cells without observations have interpolated values. GDAL reports -32768 as NoData for this raster, which the manifest records. MOLA's nominal angular posting and equatorial map scale are source-grid properties, not a claim of uniformly observed 463 m terrain detail.

PDS product page: <https://pds-geosciences.wustl.edu/missions/mgs/megdr.html>

PDS archive directory and selected tile: <https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/>

PDS label: <https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/megt44n000hb.lbl>

### Copernicus GLO-30 Public

The public mirror distributes Cloud Optimized GeoTIFFs in 1° grid objects with names of the form `Copernicus_DSM_COG_10_N18_00_E077_00_DEM/`. In this key, `10` is the mirror's GLO-30 identifier; it is not a claim that every raster axis has a 10-arcsecond posting. Copernicus product documentation gives 1-arcsecond grid spacing in latitude for GLO-30. The ingested 18°N, 77°E COG is 3,600 by 3,600 with 1-arcsecond transform spacing; the manifest records its actual 0.0002777778° pixel spacing. Product documentation defines WGS84-G1150 horizontal coordinates, EGM2008 orthometric heights in meters, and GLO-30 as a DSM that includes structures and vegetation. The public mirror's product description says its coverage is incomplete; missing objects must remain missing and are not replaced silently.

AWS object index and format notes: <https://copernicus-dem-30m.s3.amazonaws.com/readme.html>

AWS public dataset registry: <https://registry.opendata.aws/copernicus-dem/>

Official Copernicus product collection and metadata: <https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM>

## Other products considered

- LOLA documentation and PDS archive describe gridded products, including LOLA GDR. Before adding a downloader, choose the exact product/bundle, verify its current PDS4 file layout, horizontal/vertical reference and missing-value conventions, and derive an explicit lunar region product selection. Sources: <https://pds-geosciences.wustl.edu/missions/lro/lola.htm> and <https://pds-geosciences.wustl.edu/lro/lro-l-lola-2-edr-v1/lrolol_0xxx/document/archsis.htm>.
- HiRISE DTMs are delivered as PDS image products with labels. Their product-specific coordinate systems and no-data conventions must be read from each label; no generic planetary CRS or sentinel is inferred. Source: <https://hirise.lpl.arizona.edu/dtm/howto.php>.
- NASADEM/SRTM remain valid user-supplied inputs. NASA Earthdata authentication is not silently bypassed and no NASADEM downloader is claimed in this phase.

## Storage and immutability

Acquired rasters are retained under `data/raw/{body}/` and the validated raster copy is content-addressed by SHA-256. The original MOLA filename and PDS label are retained together so GDAL can reopen the detached-label product. Manifests are stored under `data/manifests/{sha256}.json`. Raw data, derived data and manifests are ignored by Git; only directory placeholders are tracked. Source bytes are read-only inputs to ingestion: ingestion copies their bytes, records checksums and does not modify them. Do not commit full source rasters.

The manifest records provider, product/version, source URL, retrieval time, checksum, size, CRS, bounds, dimensions, raster pixel spacing and spacing units, vertical units/reference, NoData, type, processing state, licensing/attribution, product-specific metadata and valid sample count. Metadata unavailable in the upstream source is represented as unavailable; CRS is never guessed.

## API and local inputs

- `GET /api/v1/datasets` returns adapter availability and validated manifests.
- `POST /api/v1/datasets/acquire/mola-jezero` acquires the explicitly selected MOLA tile.
- `POST /api/v1/datasets/acquire/copernicus-glo30?latitude=18&longitude=77` acquires one public Earth tile. Inputs identify integer degree tile origins.
- `POST /api/v1/datasets/ingest-local` accepts a basename already staged in `data/raw/{target_body}/`, plus explicit vertical units/reference and attribution. It does not accept arbitrary paths or upload data over HTTP.

Reproducible commands from the repository root:

```sh
uv run --directory backend python scripts/acquire_mola_jezero.py
uv run --directory backend python scripts/acquire_copernicus_glo30.py 18 77
```

`scripts/build_real_sample_fixtures.py` derives the compact committed test windows from these source files and records both source and sample SHA-256 values.

Remote transfers are HTTPS-only, streamed to a temporary file, size-limited, SHA-256 hashed, and published only after completion. Interrupted transfers remove their temporary files. Product-level checksum verification is recorded when the provider publishes a checksum; otherwise the manifest checksum identifies the downloaded bytes and is not misrepresented as a provider-authenticated checksum.

## Validation and tests

Run `uv run --directory backend pytest -q` and `uv run --directory backend ruff check app tests`. Synthetic rasters are used only to exercise validation edge cases. Two 64×64 compact windows are committed under `backend/tests/fixtures/data/`: one exact MOLA source window around Jezero and one exact Copernicus DSM window. Their source product IDs, source checksums, window offsets, source coordinates, sample checksums and vertical references are recorded in `sample-provenance.json`. No elevation values are fabricated. Full source files are not test fixtures and are not committed.

The end-to-end Phase 2 acceptance record, actual acquired file checksums and command output are in `documentation/validation/phase-2-report.md` after acquisition completes.
