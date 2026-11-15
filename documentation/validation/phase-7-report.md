# Phase 7 completion report — Terrain-to-Test Intelligence

Date: 2026-11-15

## Implemented

- Versioned provisional mission profile at
  `backend/config/mission_profiles/rover_mobility_and_terrain_navigation_v1.json`.
- Strict Pydantic assessment and passport contracts, deterministic evidence
  gating, source artifact verification, matching Terrain Twin lookup, and
  canonical JSON/PDF generation.
- Candidate API routes for assessment, passport, and JSON/PDF export.
- Readable candidate passport page with measured terrain comparisons,
  deterministic interpretations, validation state, provenance, missing
  evidence and limitations.
- Backend container runtime dependency for Rasterio (`libexpat1`) and packaged
  mission-profile configuration.
- Methodology, API contract and architecture decision documentation.

## Actual candidate acceptance demonstration

Generated from stored discovery, ScaleBridge, manifests and Terrain Twin
artifacts; no values were entered manually into the production assessment.

- Discovery run: `adc68c9d64de024497c0` (16 candidate windows evaluated).
- Candidate: `63af46cd196d205c2d9071d9`.
- WGS84 centroid (longitude, latitude):
  `77.35959097151041, 18.63380282807002`.
- Status: `insufficient_evidence`; rank: `null`.
- Coverage: `0.0020661157` (0.2066%) versus the run threshold `0.80`.
- Weighted distance: `null` because required evidence gates fail.
- Terrain Twin: `7a7d7e5aa32745313b158d21`, `unvalidated`; no independent
  validation metrics are claimed.
- Passport schema: `1.0.0`; passport ID:
  `c04f0694af2229d25e4b3ed3`; reproducibility SHA-256:
  `c04f0694af2229d25e4b3ed31ae8584fab75a77a72c108ac25b7ba84e818f3c2`.

Source datasets:

| Body | Product | Dataset ID / raw SHA-256 | Source support |
|---|---|---|---|
| Mars | MGS MOLA MEGDR median topography (`MEGT44N000HB`) | `14022166079edafc99650f354e5a634e6eb2c2ea544b444c01cd8ee55437df36` | 463 m raster posting; effective resolution unavailable |
| Earth | Copernicus DEM GLO-30 Public DSM | `51587b0a9af347ff0bfe95b51ccd4d145ffdf0f74fdf18ce0213028f8041d989` | 30 m nominal product; effective resolution unavailable |

Per-feature recorded distribution comparisons (measurements are shown but are
not supported similarity claims because planetary observation gates fail):

| Feature | Normalized distance ± reported SE | Mars/Earth samples | Mars/Earth coverage |
|---|---:|---:|---:|
| Slope | 0.518727 ± 0.067913 | 4 / 1849 | 0.002066 / 0.955062 |
| Local relief | 0.289516 ± 0.163713 | 9 / 1849 | 0.004649 / 0.955062 |
| Terrain roughness | 0.559218 ± 0.242073 | 9 / 1849 | 0.004649 / 0.955062 |
| Profile curvature | 2.167947 ± 0.236946 | 4 / 1849 | 0.002066 / 0.955062 |
| Plan curvature | 5.643348 ± 0.254856 | 4 / 1849 | 0.002066 / 0.955062 |
| Topographic position index | 0.575598 ± 0.229890 | 9 / 1849 | 0.004649 / 0.955062 |
| Landform morphology | 0.401839 ± 0.011372 | 9 / 1849 | 0.004649 / 0.955062 |

Feature-distance standard errors describe finite-sample variability of the
stored distribution comparisons. They are not instrument or DEM measurement
uncertainties. Because Mars support is inadequate, these numerical distances
are not asserted as Earth/Mars similarity evidence.

`data/results/evidence_passports/c04f0694af2229d25e4b3ed3/passport.json` and
`passport.pdf` were generated in ignored runtime data storage. PDF output was
verified with `pdfinfo` and `pdftotext`; it includes candidate state, counts,
feature comparisons, limitations and reproducibility references.

## Validation commands and results

- `uv run --directory backend ruff format app tests` — passed.
- `uv run --directory backend ruff check app tests` — passed.
- `uv run --directory backend mypy app` — passed, 57 source files.
- `uv run --directory backend pytest -q` — 93 passed, 1 skipped.
- `npm run lint` — passed.
- `npm run typecheck` — passed.
- `npm test` — 12 passed across 3 files.
- `npm run build` — passed; generated the dynamic candidate passport route.
- Live health endpoint — HTTP 200; PostgreSQL connected and PostGIS available.
- Live Swagger UI at `/api/v1/docs` — HTTP 200.
- Live candidate assessment — HTTP 200, `INSUFFICIENT_EVIDENCE`, null weighted
  distance, 17 findings.
- Live passport and exports — JSON API HTTP 200; JSON download HTTP 200; PDF
  HTTP 200 (`application/pdf`, `%PDF-1.4`, approximately 19 KB), including
  per-feature distribution summaries and explicit validation status.
- Docker image build initially exposed missing `libexpat1` for Rasterio in the
  slim runtime. Added the library and rebuilt; backend, frontend and database
  containers are healthy.
- Live Playwright E2E — 4 passed against the real stack, including DEM mesh
  rendering and the actual candidate passport. The passport scenario verifies
  actual sample counts, repeated boundary closure coordinates, summary
  statistics, missing soil evidence, environmental limitations and export
  links.

## Known limitations

- The actual Phase 5 candidate cannot support a similarity conclusion with
  0.2066% evidence coverage. The passport correctly gives it no rank or
  weighted distance.
- Mission weights are provisional researcher choices and need rover-domain
  review before use as validated experimental priorities.
- DEM evidence does not supply soil, traction, dust, material, gravity,
  radiation, vacuum or full-atmosphere observations.
- JSON is the complete canonical record; PDF is a readable rendering.
- Docker dependency installation reported eight moderate npm audit findings in
  the existing frontend dependency tree; remediation is outside this phase.

## Acceptance status

Phase 7 acceptance checks pass. No Phase 8 work has started. Wait for the user's
explicit approval before continuing.

## Independent audit addendum — current ranked candidate passport

The MOLA insufficient-evidence passport above is a valid earlier result. The
later HiRISE run produced a ranked candidate passport from the stored source
manifests, ScaleBridge/analytics/discovery records and actual Terrain Twin.
Candidate `2c36fc1941cc6e7bf528b0e5` is rank 1 in run
`a2070ff303aaf4cf075e`; passport schema 1.0.0, passport ID
`87a6d9aaa929fa46805523d0`, weighted distance 0.1190669273, coverage
0.9403122, validation `unvalidated`. JSON/PDF outputs are in the ignored
runtime data directory `data/results/evidence_passports/87a6d9aaa929fa46805523d0/`.
During independent audit, a candidate from an older run initially failed
assessment lookup after a newer run. Candidate-to-report lookup now searches
persisted run provenance; old-run assessment, passport, comparison and mesh
creation were retested successfully.
