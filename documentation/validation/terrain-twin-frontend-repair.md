# Terrain Twin frontend validation repair

**Date:** 2026-11-15

## User-visible correction

The Terrain Twin page now opens with the most recent completed DEM-derived
mesh and independent validation for the selected eligible candidate, when a
matching artifact exists. It also offers a reference selector for verified,
distinct bare-earth DEMs with compatible vertical units and reference. When no
comparison exists, it continues to label the mesh visualization-only and
shows explicit unavailable error and mask images.

The backend candidate feed ignores discovery runs whose Earth source is not a
verified `bare_earth_dtm`, preserves their ranking order, and excludes windows
whose polygons extend beyond the immutable source raster. It exposes weighted
distance, block-bootstrap uncertainty, evidence coverage and per-feature
distances from the persisted run. A read-only existing-mesh endpoint allows
the page to display completed results without triggering another processing
job.

## Demonstrated data

- Discovery run: `f723d7a38ca2f4afe877`.
- Bounded WGS84 Earth search extent: `[-112.72861797, 43.34060513,
  -112.60482674, 43.43083987]`.
- 25 generated windows; 25 eligible and ranked; 13 complete candidate windows
  lie fully within the original source DEM raster.
- Best reconstructible candidate: `b83aee1fc91627b419cbbfd6`, rank 3,
  distance `0.185764`, evidence coverage `94.031%`, spatial block-bootstrap
  standard error `0.019921`.
- Source: USGS 1 m bare-earth lidar DTM, product
  `USGS_1M_12_x36y481_ID_SouthernID_2018_D19`, NAVD88 metres.
- Independent reference: USGS historical 1/3 arc-second NED DEM,
  `USGS_13_n44w113_20021201`, dated 2002, NAVD88 metres. It has a distinct
  source lineage from the 2018 lidar DTM. Effective resolution is undocumented
  for both products; comparison support is nominally 10.285 m.
- Terrain Twin: `ce05abebd2df901499aeb752`; exported mesh rendered with 121,104
  vertices, 1× vertical exaggeration.
- Independent mesh comparison: 38,338 valid samples, 4.055 km² valid area,
  93.96% coverage, MAE `0.586 m`, RMSE `0.746 m`, median absolute error
  `0.478 m`, bias `0.198 m`.

These metrics are agreement with the separately acquired historical DEM at
the reported nominal support. They are not evidence of global analogue
suitability, contemporary survey accuracy, or rover performance. The candidate
is a relative terrain-distribution match within the bounded search area only.

## Verification

- Backend: Ruff clean; Mypy clean across 61 files; `110 passed, 2 skipped`.
- Frontend: TypeScript check, ESLint, and Vitest clean (`14 tests passed`).
- Frontend production build completed with
  `NEXT_PUBLIC_API_URL=http://localhost:8001/api/v1`.
- Chromium browser verification: candidate, distance and feature-level
  evidence rendered; reference preselected; saved validation loaded
  automatically; `VALIDATED` badge, error map, support mask, metrics and one
  loaded 3D canvas visible.
- Playwright service-unavailable smoke test: `1 passed`.

## Local URLs

The verified API is running at `http://localhost:8001`; the production
frontend is running at `http://localhost:3001`. The production frontend was
built with that API origin. Ports 3000 and 8000 were already occupied in the
workspace by existing TerraTwin processes, so the verified pair uses 3001 and
8001.
