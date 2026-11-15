# Phase 3 validation report: ScaleBridge

Validation date: 2026-11-14

## Scope and result

Implemented a standalone engine that accepts checksum-verified, validated raster
manifests; transforms each body's raster to its own ellipsoid-aware local metric
CRS; selects a comparison spacing that does not exceed source information;
aggregates values; propagates NoData and common support; independently centers
the two output surfaces on valid-cell medians; and writes reproducible outputs
and a structured report. No terrain features, ranking, similarity score or
analogue claim is generated. Phase 4 has not started.

The engine is directly callable and has a local real-data verification script.
It is not yet exposed through a public processing API or job service.

## Files implemented or updated

- `backend/app/domain/schemas/scale_bridge.py`: validated configuration,
  source-grid, coverage and reproducibility-report contracts.
- `backend/app/engines/scale_bridge/engine.py` and `__init__.py`: ScaleBridge
  processing, validation and artifact generation.
- `backend/app/core/exceptions.py`: explicit rejection for unsupported vertical
  units.
- `backend/scripts/run_scale_bridge_real.py`: reproducible local-data command.
- `backend/tests/scientific/test_scale_bridge.py`: analytical and edge-case tests.
- `backend/pyproject.toml`, `backend/uv.lock`: pinned Affine dependency and lock.
- `documentation/scientific-methodology/scale-bridge.md`: processing method and
  limits; architecture and roadmap files updated to reflect Phase 3.
- `README.md` and this validation report: current implementation status and
  acceptance evidence.

Derived rasters and their JSON report are in ignored `data/processed/`; no large
source data or generated terrain artifacts were added to Git.

## Real-data run

Command, run from the repository root:

```sh
uv run --directory backend python scripts/run_scale_bridge_real.py \
  --mars-center 77.5 18.4 --earth-center 77.5 18.5 \
  --support-width-m 20000 --support-height-m 20000
```

The run used the actual Phase 2 raw files and detached MOLA label:

| Input | Product identifier | Input SHA-256 | Native CRS and units | Measured local spacing at center | Vertical reference |
|---|---|---|---|---:|---|
| Mars | MOLA `MEGT44N000HB.IMG` | `14022166079edafc99650f354e5a634e6eb2c2ea544b444c01cd8ee55437df36` | MOLA simple cylindrical; metres | 439.329 m x, 463.000 m y | GMM3 Mars areoid-referenced radial topography |
| Earth | Copernicus DEM GLO-30 Public DSM tile `COP-DEM-GLO30-18-77` | `51587b0a9af347ff0bfe95b51ccd4d145ffdf0f74fdf18ce0213028f8041d989` | EPSG:4326; degrees | 29.334 m x, 30.746 m y | EGM2008 orthometric height |

The 20 km requested support produced a **44 × 44** comparison grid at
**463.000000 m** cell size. The actual centered support is 20,372 m per side
because grid dimensions are rounded up to whole cells. All 1,936 cells passed
the 0.999 per-cell valid-source fraction for each input, yielding 100% paired
coverage and 415,018,384 m² projected grid area. The projected-area figure is
cell count × cell size squared; it is not a geodesic area calculation.

Each DEM was averaged independently into its own local CRS and centered on its
own valid-cell median after conversion to metres. The MOLA and Earth vertical
references were not reconciled, and no absolute cross-body elevation difference
was computed. The report flags unavailable effective resolution for both
products and MOLA's product-documented interpolated cells. The 463 m decision is
a conservative cell-spacing floor, not a claim that MOLA resolves 463 m terrain.
Copernicus's finer DSM data were aggregated; their finer detail is not present
in the comparison outputs.

Output directory:
`data/processed/scale_bridge/99e49fbaf65274904f36/`

| Output | Format / semantics | SHA-256 |
|---|---|---|
| `planetary_relative_elevation.tif` | 44 × 44 Float32 GeoTIFF in Mars local metric CRS; metres relative to the MOLA support median | `11045effcf684c780a1dd60a31bc38c27b43d1d915b514d9681f1662144f0742` |
| `earth_relative_elevation.tif` | 44 × 44 Float32 GeoTIFF in Earth local metric CRS; metres relative to the Copernicus support median | `ea6c73274f31cdb4ec145b613bc13b135141f2331738f20080db5322d0b69a73` |
| `common_support_mask.npy` | 44 × 44 Boolean pair-index mask; no single-body CRS | `64b8a864835009506d968ae323d1c6a948de1b0e61506a81a61aed7333b27e39` |
| `report.json` | Machine-readable processing report, configuration digest, bounds, resolution, masks, warnings and artifact checksums | Recorded outside its own checksum map |

Run ID: `99e49fbaf65274904f36`; full reproducibility digest:
`99e49fbaf65274904f3641da3fdf1ffe4c86404fc25a311e41db10f857cddf88`.
Software versions recorded by the run: TerraTwin ScaleBridge 0.1.2, NumPy 2.5.4,
Rasterio 1.5.2, GDAL 3.12.2, PyProj 3.7.2 and PROJ 9.5.1. The script verified
input checksums before processing; a post-run hash check confirmed both source
rasters still match their manifests. Output checksums were independently
recomputed and matched the report.

## Scientific tests

`backend/tests/scientific/test_scale_bridge.py` exercises the public engine with
explicit synthetic analytical surfaces (test data only):

- Flat surfaces remain zero after independent median centering.
- A constant slope retains the expected direction and approximately expected
  gradient after aggregation.
- Gaussian hill and bowl preserve their center-to-edge relief sign.
- Sinusoidal terrain retains both positive and negative relief.
- Differing source spacings select the coarser support; requesting finer
  comparison resolution is rejected, and documented effective resolution
  raises the target floor where it exceeds nominal sampling.
- NoData cells remain missing and reduce paired coverage rather than becoming
  zero elevations.
- Invalid CRS and unsupported vertical units are rejected; feet are converted
  to metres before centering.
- Repeating the same inputs and configuration produces the same run digest and
  numerical output.
- Separate local CRS centers transform to their respective local origins, and
  the output rasters, mask and report are persisted with checksums.

## Validation commands and results

- `backend/.venv/bin/pytest backend/tests -q -ra` — **39 passed, 1 skipped**.
  The skipped case is the opt-in live PostGIS integration test.
- `RUN_DB_TESTS=1 backend/.venv/bin/pytest backend/tests/integration/test_database.py -q -ra`
  with elevated host network access — **1 passed**; PostgreSQL connectivity and
  PostGIS availability/version were confirmed.
- `backend/.venv/bin/ruff format --check backend/app backend/tests backend/scripts`
  — all 62 files formatted.
- `backend/.venv/bin/ruff check backend/app backend/tests backend/scripts` — all
  checks passed.
- `backend/.venv/bin/mypy --strict backend/app` — no issues in 43 source files.
- `UV_CACHE_DIR=/tmp/terratwin-uv-cache uv lock --check --directory backend` —
  dependency lock validates after pinning Affine 3.0.1.
- `uv sync --locked --directory backend` — locked project environment built and
  synchronized successfully.
- `docker compose config -q` and `git diff --check` — passed.
- Real-data script command above — completed; both output GeoTIFFs reopened with
  Rasterio and report artifact checksums matched the files.
- Raw MOLA and Copernicus source checksums after the run matched their Phase 2
  manifests.

## Known limitations

- Effective resolving power and uncertainty are not present in the acquired
  manifests; nominal pixel spacing is not a substitute for them.
- MOLA's MEGDR includes interpolated bins; the source does not provide a
  per-pixel observed-versus-interpolated mask in the ingested product.
- Copernicus GLO-30 is a DSM with vegetation and built structures.
- Each support center must be selected by the caller. Same-sized support does
  not mean the locations are geographically coincident or physically
  equivalent.
- Area is calculated in the local projected grid; no geodesic area correction
  is applied.
- The current API does not expose ScaleBridge as an asynchronous job.

## Acceptance status

| Acceptance item | Result |
|---|---|
| Real Mars and Earth DEMs processed | Pass — MOLA MEGT44N000HB and Copernicus GLO-30 |
| CRS handled explicitly | Pass — Mars and Earth receive separate ellipsoid-aware local metric CRSs |
| Comparison resolution documented | Pass — 463.000 m chosen from measured local source spacing; effective resolving power unavailable |
| NoData propagated and coverage calculated | Pass — 100% valid support for this real run; independent synthetic NoData case passes |
| Incompatible data warns or rejects | Pass — invalid CRS, unsupported units and over-fine target rejected; vertical reference differences reported |
| Synthetic numerical tests | Pass — flat, slope, hill, bowl, sinusoid, missing-data, effective-resolution and unit cases |
| Reproducibility and source immutability | Pass — configuration digest and output checksums verified; inputs unchanged |
| Phase 4 started | No |

**Phase 3 acceptance passes. Stop here pending explicit approval for Phase 4.**

## Independent audit addendum — unequal supports and HiRISE

Subsequent integrated processing added a 2.000 km Mars HiRISE reference
support while retaining a wider Earth search support. The earlier equal-grid
pair-mask semantics are not applicable when those outputs have different
dimensions. ScaleBridge now reports independent per-body coverage and null
paired coverage in that case. A regression check found and corrected the
planetary coverage denominator for unequal grids. The current run
`5307327b9e0163613f7e` aggregates HiRISE to the coarser local Earth posting
(30.7461555 m), producing a 66×66 Mars grid and 326×326 Earth grid, with
separate actual supports of 2,029.246 m and 10,023.247 m. Neither absolute
vertical datums nor effective resolutions are silently equated. See
[`independent-phase-audit.md`](independent-phase-audit.md) and the run report.
