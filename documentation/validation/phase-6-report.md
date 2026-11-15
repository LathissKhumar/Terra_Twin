# Phase 6 validation report — Terrain Twin and independent validation

**Run date:** 2026-11-15  
**Acceptance status:** Phase 6 implementation and software checks pass. Metric
validation of the demonstrated terrain is `UNVALIDATED` because no suitable
independent reference DEM is currently available in the local catalog. Phase 7
has not started.

## Subsequent scientific correction and live demonstration

This report's initial validation status is historical. The following follow-up
was completed on 2026-11-15 after the independent scientific audit identified
the missing reference-data path. The Terrain Twin API now selects only the
latest discovery run whose verified Earth source manifest identifies a
`bare_earth_dtm`, and filters out candidate polygons that extend beyond that
immutable source raster. Ranked order is retained among supported candidates.
The page now provides an explicit selector for a separate, checksum-verified
reference with matching bare-earth classification, vertical units/reference,
and non-overlapping lineage.

Demonstrated run: discovery `f723d7a38ca2f4afe877`, 25 generated and evaluated
windows, all 25 eligible and ranked over the bounded Idaho search envelope
`[-112.72861797, 43.34060513, -112.60482674, 43.43083987]` (WGS84). The top two
windows touch beyond the source DEM footprint and are not offered to mesh
generation. The highest-ranked fully covered window is candidate
`b83aee1fc91627b419cbbfd6`, rank 3, weighted terrain distance `0.185764` under
mission profile v1.1.0, evidence coverage `94.03%`. This is a relative
methodological ranking within this finite search, not a universal suitability
claim.

The generated Terrain Twin is `ce05abebd2df901499aeb752`, with 121,104 mesh
vertices and 1× vertical exaggeration. Independent comparison used USGS
historical NED product `USGS_13_n44w113_20021201` (2002, NAVD88 metres),
distinct from the source 2018 USGS lidar project. The exported mesh surface and
reference were area-averaged to nominal common support 10.285 m. Results:
38,338 valid samples; 4,055,450.91 m² valid area; 93.956% valid coverage; MAE
0.58577 m; RMSE 0.74626 m; median absolute error 0.47833 m; mean bias 0.19758 m.
Effective resolution is undocumented for this pair, and the older NED is not
contemporary ground truth. These metrics validate agreement with that
independent reference at the reported nominal support only; they do not
validate planetary analogue suitability or the discovery ranking.

The frontend displays the eligible supported candidate, independent DEM
selector, loaded GLB, validation status, error map, valid support mask and
comparison metrics. A headless Chromium check confirmed the mesh renderer
reached `loaded` with one canvas and the selected historical reference. Backend
Terrain Twin tests: 10 passed before the report-selector correction; 2 API
route tests passed after it. Frontend typecheck, lint and component tests were
run (14 tests passed); rerun after the last selector metadata edits is tracked
in the current task's completion report.

## Implemented

- Candidate-scoped backend reconstruction route using actual Phase 5 report
  records and manifest/checksum-resolved Earth rasters.
- Local projected metric raster creation, explicit source and target postings,
  validity-mask reprojection, safe normals, stride sampling and chunked GLB 2.0
  export with geographic/vertical/provenance metadata.
- True source NoData accounting separated from candidate-polygon exterior.
  Triangles are omitted if their contributing cell footprint touches invalid
  data.
- An independent DEM comparison engine with same-source, unit, CRS, common
  support and vertical-reference checks; MAE, RMSE, median absolute error, bias,
  percentiles, sample count, area and coverage are available only on a valid
  independent comparison.
- Candidate viewer in the Next.js app with actual GLB loading, orbit/pan/zoom,
  reset, elevation and slope coloring, wireframe, source and reconstruction
  metadata, preview maps, and explicit unavailable validation graphics.
- API tests using the documented compact real Copernicus raster fixture and
  scientific tests for NoData triangles, mesh structure, masks, manual error
  statistics, datum mismatch, same-source rejection, provenance and source
  immutability.

## Earlier real-data run (superseded)

The latest Phase 5 run was `adc68c9d64de024497c0`. The selected candidate was
`63af46cd196d205c2d9071d9`; it is recorded as `insufficient_evidence` with no
rank. It was used to demonstrate reconstruction only, not as an analogue
finding. The generated terrain twin is `7a7d7e5aa32745313b158d21`.

This initial unvalidated example is retained as historical record. It is
superseded by the independent reference demonstration and corrections
documented above and in the follow-up addendum below.

| Item | Observed value |
|---|---|
| Earth product | Copernicus DEM GLO-30 Public DSM, 2021 release |
| Product tile | `COP-DEM-GLO30-18-77`, source tile N18/E077 |
| Original raster | GeoTIFF, 3600 × 3600, EPSG:4326, 1 arc-second posting |
| Elevation | metres, EGM2008 orthometric height; DSM surface |
| Source checksum | `51587b0a9af347ff0bfe95b51ccd4d145ffdf0f74fdf18ce0213028f8041d989` |
| Candidate WGS84 bounds | 77.2629323271, 18.5416816623 to 77.4561456863, 18.7258740890 |
| Mesh CRS | EPSG:32643; east/north metres |
| Mesh posting | 30.7462 × 30.7462 m; conservative metric posting from source ground spacing |
| Projected raster | 673 × 673 cells |
| Elevation range | 372.50–527.55 m |
| Mesh | GLB 2.0, 6,769,012 bytes, 114,921 vertices, 9 chunks, stride 2, 1× vertical exaggeration |
| Candidate crop accounting | 460,548 cells inside candidate; 0 source NoData; 1,596 cells outside polygon in crop rectangle |
| Projected invalid cells | 13,542, including projected rectangular edge outside the candidate footprint |
| Validation | `UNVALIDATED`; no independent reference selected; metrics null |

The source checksum matched before and after reconstruction. A cold direct
engine run took 0.531 s in this development environment and the process peak
resident memory was 210,316 KiB (including the Python, GDAL, NumPy and other
already loaded runtime). The API returned the GLB with `model/gltf-binary` and
the correct `glTF` version-2 header. A browser run loaded it into a WebGL canvas.

## Validation and quality commands

| Command | Result |
|---|---|
| `uv run --directory backend ruff check app tests` | Passed |
| `uv run --directory backend ruff format --check app tests` | Passed; 70 files formatted |
| `uv run --directory backend mypy app` | Passed; 51 source files |
| `uv run --directory backend pytest -q` | 84 passed, 1 skipped (database-dependent test) |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed |
| `npm test` | Passed; 2 files, 11 tests |
| `npm run build` | Passed; production build generated `/` and `/_not-found` |
| `LIVE_STACK=1 PLAYWRIGHT_BASE_URL=http://localhost:3001 PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:e2e` | Passed; 3 tests, including real API mesh generation, GLB browser loading, validation state and viewer controls |
| API GET candidates / POST create / GET metadata / GET artifacts | 200 / 201 / 200 / 200; GLB, elevation, slope and explicit unavailable artifacts returned |

One initial regression test caught GDAL reclassifying mask zero during warp;
categorical validity codes were changed to reserve zero and 255, and a
regression test now covers it. A metadata review then found that crop-rectangle
cells outside the candidate polygon had been counted as source NoData. The
output now separates those counts, and the full test suite was rerun.

## Independent-reference decision

No independent, locally ingested Earth reference raster with verified matching
vertical reference was available for this candidate. The Copernicus source is
EGM2008 orthometric height. NASADEM is documented in EGM96 for the merged
integer elevation product; no validated vertical transformation grid is
configured here, so it was not combined to manufacture an error metric. The
viewer labels this result `UNVALIDATED`, displays no validation measurements,
and presents explicit unavailable error-map and common-support artifacts.
See the [NASADEM User Guide](https://lpdaac.usgs.gov/documents/2237/NASADEM_User_Guide_V13.pdf).

## Files added or changed for Phase 6

- Backend: `app/domain/schemas/terrain_twin.py`, `app/engines/terrain_twin/engine.py`,
  `app/engines/validation/engine.py`, `app/api/routes/terrain_twin.py`,
  `app/api/api_v1.py`, `tests/scientific/test_terrain_twin.py`,
  `tests/api/test_terrain_twin.py`.
- Frontend: `features/terrain-twin/terrain-mesh-viewer.tsx`,
  `features/terrain-twin/terrain-twin-workbench.tsx`,
  `types/terrain-twin.ts`, `lib/terrain-twin-api.ts`, `app/page.tsx`,
  `app/icon.svg`, Playwright configuration and end-to-end test.
- Documentation: `architecture/terrain-twin.md`,
  `scientific-methodology/terrain-twin.md`, this report, and ADR 0003.
- Dependencies: pinned Three.js and matching TypeScript declarations.

## Limitations and outstanding items

- The selected Phase 5 candidate remains insufficient evidence and unranked;
  visualization does not change that scientific state.
- Copernicus GLO-30 is a DSM, not bare-earth terrain, and its surface returns
  can include vegetation and structures.
- No independent reference metrics were computed. A compatible, separately
  sourced, datum-matched reference raster and documented independent check are
  still needed for a metric-validation demonstration.
- The reported performance is one small candidate window on this development
  machine; it is not a large-raster benchmark. Input and output bounds are
  enforced, but distributed processing is not introduced.
- No geology, soil behavior, or image-derived depth is inferred.

## Acceptance gate

1. Real candidate DEM converted to a 3D mesh: **Pass**.
2. Geographic extent and coordinate metadata preserved: **Pass**.
3. Elevation units and vertical reference preserved with 1× default scale: **Pass**.
4. NoData/exterior handled, classified separately, and triangles do not bridge invalid cells: **Pass**.
5. Mesh exported and served successfully: **Pass**.
6. GLB loaded by Three.js in a browser; controls exercised: **Pass**.
7. Independent validation: **Unavailable; honestly marked `UNVALIDATED`, no metrics claimed**.
8. Processing/provenance and validation limitations documented: **Pass**.

**Phase 6 status:** implementation accepted for review. Stop here and wait for
explicit approval before Phase 7.

## Independent audit addendum — ranked HiRISE-run candidate

The earlier unranked MOLA candidate remains a historical reconstruction test.
The later run `a2070ff303aaf4cf075e` supplied a rank-1 Earth candidate and
produced Terrain Twin `00f5f757604e98189edd7391` from its actual Copernicus
DEM. Its GLB (275,284 bytes), elevation map and slope map were returned through
the API, and Playwright confirmed the browser mesh renderer loaded. The mesh
uses EPSG:32643, metre elevations referenced to EGM2008 and 1× vertical
exaggeration. No independent, datum-compatible validation DEM is available;
status remains `UNVALIDATED`, metrics null, and the reason is recorded in
metadata. The audit does not reinterpret visualization as metric validation.
