# Terrain comparison page repair

Date: 2026-11-15

## Result

The comparison view now opens the latest completed discovery run, orders candidates by their recorded rank, presents readable source and comparison CRS labels, and shows both actual feature-map previews alongside measured statistics and valid sample counts. Landform morphology is presented as its measured relative-low, neutral, and relative-high class fractions rather than as an unavailable median. If a comparison cannot be fetched, the page offers a return to discovery and does not claim that a network error proves the data are missing.

No values or map pixels were fabricated.

## Verified real comparison

- Discovery job: `f483def7-719c-4340-a404-fc320344f6c2`
- Discovery run: `e73b33dc06a4abf10cc0`
- Planetary source: HiRISE stereo-derived Jezero DTM
- Earth source: USGS 1 Meter bare-earth DEM, tile `12 x36y481`, project `ID_SouthernID_2018_D19`
- Search boundary (WGS84): `[-112.72861797267058, 43.34060512767353, -112.60482674303144, 43.43083986991839]`
- Generated/evaluated/eligible candidates: `25 / 25 / 25`
- Top candidate: `fef99825d89c959aab0185af`, rank 1
- Weighted terrain distance: `0.1299336473` (lower means closer under this configured feature set and profile; not universal suitability)
- Evidence coverage: `94.031%`
- Slope medians: Mars `1.02949°`, Earth `1.06479°`
- Slope valid samples: Mars `4,096`, Earth `4,290`
- Slope normalized distribution distance: `0.100203`
- Example class fractions (relative low / neutral / relative high): Mars `8.9% / 82.0% / 9.1%`; Earth `3.5% / 88.0% / 8.5%` (rounded display values).

Earth search was bounded to the recorded Idaho study region; the ranking is not a global search or a claim of novelty. Mission weights are provisional configuration choices. The run reports source effective-resolution limitations and cautions that its reported bootstrap variability does not account for spatial autocorrelation or source DEM measurement uncertainty.

## Why an older page may still show unavailable

The previously opened run `a35f8d3b57790cde7ff1` uses MOLA over a 5 × 5 planetary analytics grid. Its planetary input has sparse support, and the requested slope comparison has zero valid planetary feature samples. The correct scientific display for that run is “unavailable”; inventing numbers would be misleading. The page now guides users back to the completed HiRISE comparison, which has measured support on both sides.

## Verification executed

- `docker compose up -d --build backend frontend` and a subsequent frontend rebuild: containers started; backend, frontend, and PostGIS database reported healthy.
- `GET /api/v1/health`: healthy; database connected; PostGIS 3.4 available.
- Live Playwright test `shows genuine Mars and Earth feature maps and measured comparison values`: passed. It checked the ranked candidate, readable CRS text, feature cards, all 14 map previews loading in the browser, numeric summaries, and landform fractions.
- Frontend: typecheck passed; lint passed; 4 test files and 14 tests passed.
- Backend: Ruff passed; mypy passed on 61 source files; pytest `110 passed, 2 skipped`.
- `git diff --check`: passed.

One existing warning remains: Starlette deprecates the current `httpx` integration through its test client. It did not fail the suite.
