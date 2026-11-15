# Discovery 503 and ScaleBridge configuration repair

Date: 2026-11-15

## Findings and corrections

- The reported candidates endpoint 503 came from a valid saved report written
  before `planetary_surface_type` and `earth_surface_type` were added to the
  report schema. Those fields are now optional and serialize as `null` when the
  historical provenance is absent. The report's values are not guessed.
- A failed run requested a 50 km grid at approximately 1 m source spacing,
  exceeding ScaleBridge's four-million-cell safety bound. ScaleBridge now
  coarsens only as needed to meet that explicit bound, never below measured or
  documented source support, and records the actual resolution and warning.
- Discovery now requests a 30 m comparison support explicitly and defaults to
  a 10 km Earth search support. Selecting a coarse metric planetary raster
  updates the visible window defaults from its manifest resolution. MOLA
  `MEGT44N000HB` uses a 50 km planetary reference support because its valid
  direct-observation coverage around the selected Jezero center is sparse.

## Verification with actual stored data

- Historical candidates request for job
  `afd4ec79-d908-4d16-8002-689645ded771` now returns HTTP 200. Its 16 candidates
  remain `insufficient_evidence`; zero are ranked. This is the scientifically
  honest state for its MOLA/Copernicus DSM report.
- Reprocessed MOLA job `a3c8e149-ff54-403e-a0ee-7502b3a92bb7` completed through
  ScaleBridge, terrain analytics, and discovery. The actual ScaleBridge grid
  used 463.0000002 m cells (108 × 108 Mars cells; 22 × 22 Earth cells), not the
  requested 30 m. Its report explicitly says the target was coarsened to
  measured MOLA support and that no upsampling occurred.
- MOLA valid-cell coverage was 9.285%, below the configured 80% evidence gate.
  The discovery run therefore generated 16 candidate windows but ranked none.
  It is no longer reported as a ScaleBridge or processing error.
- The current HiRISE-to-USGS bare-earth run remains restored by default. Live
  Playwright verified its rank-1 comparison and measured Mars/Earth results.
- Playwright also verified that selecting the MOLA manifest updates the visible
  planetary support to 50 km and candidate window to 5 km.

## Checks

- Backend Ruff and mypy: passed.
- Backend pytest: `112 passed, 2 skipped`.
- Frontend typecheck, lint, and tests: passed; `14 tests`.
- Live Playwright tests for the HiRISE comparison and coarse MOLA defaults:
  `2 passed`.
- Docker backend, frontend, and PostGIS containers: healthy.
