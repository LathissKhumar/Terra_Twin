# Phase 8 integration and validation report

Date: 2026-11-15  
Scope: connect the previously built scientific engines to the FastAPI service,
persist discovery jobs, expose their actual results in the frontend, and
exercise the integrated local stack. This report records implementation and
validation evidence; it does not certify the platform as production-ready.

## Delivered

- Mounted versioned mission, dataset, discovery, terrain-comparison,
  terrain-twin, assessment and evidence APIs.
- Added PostgreSQL-backed discovery job records, request fingerprints,
  duplicate suppression, bounded one-worker execution, progress and sanitized
  error state, restart recovery, and staged publication of complete artifacts.
- The worker validates dataset IDs against manifests and checksums, passes the
  detached MOLA label to GDAL, then calls the existing ScaleBridge, Terrain
  Analytics and Analogue Discovery engines. The frontend does not calculate
  scientific results.
- Added mission/source selection, explicit planetary and Earth centers,
  dataset acquisition and GeoTIFF upload, physical search configuration,
  persistent status polling, candidate/evidence views, feature-map previews,
  comparison metadata, mesh viewer, assessment and JSON/PDF passport views.
- Added database integration, API, scientific regression and UI/E2E coverage;
  updated setup, architecture, API and scientific-method documentation.

Key implementation areas: `backend/app/services/discovery_jobs.py`,
`backend/app/api/routes/`, `backend/app/domain/models/discovery_job.py`,
`frontend/features/analogue-discovery/`, `frontend/features/terrain-twin/`,
`frontend/features/evidence-passport/`, Compose and Alembic configuration.

## Actual source inputs and search result

The live run used the manifests already present in TerraTwin's data store:

| Input | Actual product | Manifest ID (SHA-256) | Source raster size |
|---|---|---|---:|
| Mars | MOLA MEGDR `MEGT44N000HB`, dataset `MGS-M-MOLA-5-MEGDR-L3-V1.0` | `14022166079edafc99650f354e5a634e6eb2c2ea544b444c01cd8ee55437df36` | 129,761,280 bytes |
| Earth | Copernicus DEM GLO-30 DSM `COP-DEM-GLO30-18-77` | `51587b0a9af347ff0bfe95b51ccd4d145ffdf0f74fdf18ce0213028f8041d989` | 39,715,598 bytes |

The MOLA tile is the 0–44°N, 0–90°E northern tile. Its grid posting is about
463 m; that posting is not interpreted as uniform independent terrain
resolution. The Earth source is one 3,600 × 3,600, 1-arcsecond GLO-30 tile
covering 77–78°E, 18–19°N. See the [Phase 2 report](phase-2-report.md) for
source links, detailed CRS and vertical metadata, acquisition checksums and
source limitations.

Successful job:

- Job ID: `679634e4-07ce-4361-a265-d81611a251c4`
- Discovery run ID: `df00a376fc284dfe5450`
- Search boundary (WGS84 lon/lat bounds):
  `[77.2629323271279, 18.27396810860149, 77.73706767287212, 18.72587919382713]`
- Comparison support: 50,000 m × 50,000 m; target cells about 463 m.
- Candidate windows: 20,000 m × 20,000 m, 10,000 m stride.
- Generated/evaluated: 16; eligible: 0; ranked: 0.
- Planetary feature coverage was approximately 0.2066% for the candidate
  support (feature-specific coverage varies). Earth support coverage was about
  95.5%. All candidates were marked `INSUFFICIENT_EVIDENCE`; weighted distance
  and rank are null.

This is an actual result, not a fabricated discovery. The very sparse valid
MOLA observation support makes the selected comparison insufficient. The
system returns that limitation rather than weakening the evidence threshold or
inventing terrain. It does not constitute an Earth-wide search.

The generated Terrain Twin used a 664 × 696 Copernicus crop and produced a
673 × 673 mesh grid, 114,921 vertices and 9 chunks at approximately 30.746 m
mesh spacing, with vertical exaggeration 1.0. No independent reference DEM was
selected, so the validation status is `UNVALIDATED`, metrics are null, and the
reported reason is “No independent reference DEM was selected.”

## Executed validation

Commands and observed results:

| Check | Result |
|---|---|
| `RUN_DB_TESTS=1 uv run pytest -q` from `backend/` | 97 passed; one Starlette deprecation warning about `httpx` integration |
| `uv run ruff check app tests migrations` | Passed after resolving import ordering |
| `uv run ruff format --check app tests migrations` | Passed |
| `uv run mypy app` | Passed |
| `npm ci --ignore-scripts` in `frontend/` | Completed |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed |
| `npm test -- --reporter=dot` | 14 tests passed across 4 files |
| `npm run build` | Passed; Next.js generated all integrated routes |
| `npm audit` | 0 vulnerabilities after pinning the transitive `minimatch` override |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium LIVE_STACK=1 npx playwright test --reporter=list` | 2 E2E tests passed against the live Compose stack |
| `docker compose ps` | frontend, backend and PostGIS containers healthy |
| `GET /api/v1/health` | HTTP 200; PostgreSQL 16.4 connected; PostGIS 3.4 available |
| `GET /api/v1/docs` | Swagger UI opened successfully in live browser journey |
| Candidate comparison and feature preview | HTTP 200; JSON comparison and Mars slope PNG returned from actual run `df00a376fc284dfe5450` |
| Assessment and Evidence Passport | HTTP 200; actual candidate assessment and canonical passport returned |
| Passport JSON and PDF export | HTTP 200 for both; PDF content type `application/pdf`, `%PDF-1.4`, 19,083 bytes |
| Terrain Twin metadata and mesh artifact | HTTP 200; validation is `unvalidated`, metrics are null; GLB returned as `model/gltf-binary`, 6,769,012 bytes |
| Identical discovery submission | Existing matching job reused (`reused_existing_job: true`) |
| Upload filename `../escape.tif` | Rejected with structured HTTP 415; traversal was not accepted |
| Invalid raster upload | Rejected with HTTP 400; no local filesystem path exposed |
| Backend restart | Health recovered; a deliberately stale `running` record was marked `interrupted` with `WorkerInterrupted` |
| Database restart | Health recovered and PostGIS remained available |
| Live browser product journey | Mission selection → discovery configuration/job results → candidate comparison → mesh → passport views completed; no fabricated measurements were displayed |

The Playwright browser binary download from its configured CDN stalled during
installation, so the test used the available system Chromium at
`/usr/bin/chromium`. The E2E tests completed successfully with that executable.
The host Chromium emitted Node/browser compatibility warnings, but no test
failed.

The API response timings sampled during integration were approximately 7.47 ms
for health, 10.23 ms for mission metadata, and 11.31 ms for a candidate page
in this local environment. A discovery job took approximately 7.92 seconds.
These are single local observations, not statistically controlled benchmarks.
A sampled post-job backend memory reading was approximately 331 MiB; it is not a
peak-memory measurement. No broad load test or peak RSS profiling was done.

## Error handling, persistence and security review

- Jobs are stored in Postgres and status survives page refresh. Startup marks
  previously running records interrupted and does not expose their incomplete
  result as a successful candidate set. Queued records are resubmitted.
- Repeated identical active or successful requests reuse their durable job.
  The in-process queue is bounded and returns a capacity error when full.
- Input schemas constrain geographic bounds, dimensions, and candidate counts.
  Dataset selection uses manifest identifiers; path traversal is rejected;
  raster paths are resolved beneath configured stores and verified against
  recorded SHA-256 values.
- Processing writes to a staging directory and publishes completed engine
  artifacts only after all stages succeed. Temporary job staging is cleaned
  after success or failure.
- API failures return structured errors without returning arbitrary internal
  exception text or configured filesystem paths. Compose binds service ports
  to loopback.
- Recovery was manually exercised by interrupting a persisted running job.
  After rebuilding the final backend image, a test row with a deliberately
  stale result ID was changed to `interrupted`, stage `interrupted`, result ID
  null and `WorkerInterrupted`; the test row was deleted. The actual successful
  discovery artifacts and job record remain available.

## Outstanding acceptance gaps and limitations

- The scientifically correct result currently has zero eligible candidates.
  The local MOLA observation-count evidence covers too little of the comparison
  support; this is not evidence that the candidate generator found no possible
  analogues globally. Better supported planetary topography is needed to make
  the initial Jezero comparison useful.
- The Earth collection is one GLO-30 tile. The product accepts other real Earth
  sources, but no global scan or geographically broad discovery was executed.
- There is no independent elevation reference for the generated mesh; its
  status remains `UNVALIDATED`.
- Moon is represented as unavailable unless a validated lunar dataset has
  been ingested. No automatic LOLA downloader was enabled.
- The worker is one in-process thread per backend instance. Multiple backend
  replicas lack an atomic database lease, and crash recovery marks running
  jobs interrupted rather than resuming their partial computation.
- There is no user authentication or authorization, rate limiting, TLS
  termination, upload quota enforcement at the deployment boundary, or
  production operations profile. Local Compose must not be published directly
  to an untrusted network.
- Benchmarking was limited to a single actual discovery job and sampled API
  timings. Concurrency, large-area processing, browser memory ceilings,
  backup/restore drills and resource-exhaustion behavior remain unverified.
- E2E demonstrated app interactions against actual processed records but did
  not produce a ranked candidate, because the scientific evidence gate properly
  left all candidates unranked.

## Acceptance status

Phase 8 integration implementation and its local automated/live validation
checks are complete. The stack runs, APIs and frontend are connected, durable
jobs execute the scientific pipeline, and the actual outputs and limitations
are visible. The master end-to-end scientific acceptance gate is **not fully
met**: no candidate is rankable with the available MOLA evidence, no
independent terrain validation data is available, and the Earth search covers
only one tile. TerraTwin is **not production-ready**. Stop here pending the
user's review; do not start another phase without explicit approval.

## Independent audit addendum — superseding HiRISE end-to-end run

The MOLA result above documents the earlier integration state. The later
independent audit rebuilt the current production/frontend images, corrected
candidate-to-run lookup and proxy docs routing, then ran the actual Playwright
journey with the HiRISE Jezero DTM. The journey submitted a new job, verified
that job ID across reload, checked HiRISE provenance in the persisted report,
and required a nonzero ranked result. Run `a2070ff303aaf4cf075e` evaluated and
ranked 25 windows in the explicitly bounded 10 km Earth search. The user flow
opened candidate comparison, assessment, passport, and a browser-rendered GLB;
the independent validation state was visibly `UNVALIDATED`. JSON and PDF
passport exports returned successfully.

The local production Compose stack also built and started from a temporary
smoke environment. HTTPS served the frontend; `/api/v1/health`, `/api/v1/docs`
and `/api/v1/openapi.json` returned 401 without credentials and 200 with the
temporary smoke credential. Health confirmed PostgreSQL 16.4 and PostGIS 3.4;
migrations completed and inspected backend/proxy logs had no application error.
The isolated smoke containers, volumes, temporary credentials and data were
removed afterward.

This audit's acceptance decision supersedes the older statement above for
local single-tenant deployment: the integrated bounded workflow passes, while
independent metric validation, wider Earth coverage and public multi-user
security remain constrained. TerraTwin is ready for controlled single-tenant
deployment when a real host/domain, persistent data location and backup
destination are configured. It has not been deployed externally. See
[`independent-phase-audit.md`](independent-phase-audit.md).
