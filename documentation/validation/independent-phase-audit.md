# TerraTwin independent audit — Phases 1–8

Audit date: 2026-11-15  
Scope: independently inspect and exercise the repository's eight completed phases, verify numerical and product acceptance evidence, fix audit findings, and retest. No later phase was started.

## Executive result

The end-to-end scientific workflow now runs on actual Mars and Earth elevation data. The audited live browser flow selected HiRISE `DTEEC_048842_1985_048908_1985_U01` for Jezero and the Copernicus GLO-30 tile `COP-DEM-GLO30-18-77` for Earth, submitted and resumed a new job, produced 25 evidence-eligible ranked windows in the bounded Earth area, rendered an actual DEM-derived mesh, and generated the assessment and JSON/PDF passport. No trained model is used.

**Phase acceptance:** Phases 1–8 pass their implemented software and workflow gates, subject to the scientific limitations below. The six acceptance items requiring valid measurements are backed by the actual run `a2070ff303aaf4cf075e`; the reconstruction's independent accuracy validation is explicitly `UNVALIDATED` because no suitable independently sourced, datum-compatible reference DEM is available. No validation metrics were fabricated.

**Deployment status:** the production Compose stack was built and smoke-tested locally, including TLS termination, authentication, frontend/API routing, migrations, PostgreSQL and PostGIS. TerraTwin has not been deployed to an external host: no host, DNS name, cloud account or operator credentials were supplied. The production configuration is a single-tenant deployment with shared HTTP Basic Authentication; it is not a multi-user identity service.

## Repository and architecture review

- Reviewed the current changes and phase validation reports across `backend/app`, `backend/tests`, `frontend/`, `deployment/`, Compose, manifests and architecture/scientific documentation. Runtime data products remain ignored and are not checked into source control.
- One duplicate behavior was found: three candidate-facing paths had independent latest-report/search logic. A common candidate-to-run resolver now owns that lookup; the Terrain Twin list still intentionally lists only the newest run, while candidate-scoped APIs resolve the selected candidate's own persisted run.
- No circular import surfaced during application startup, module imports, mypy or API tests. This was not a formal graph-theoretic import-cycle scan.
- No unused runtime dependency was identified from the reviewed imports; dependencies correspond to API/database, raster/CRS/array processing, PDF and image output. A dedicated dependency-usage scanner was not run.
- Versioned provisional mission weights and supported product identifiers are intentional configuration choices, not hidden candidate coordinates. The bounded Earth search and single mission profile are documented.
- Historical plan/report documents still describe earlier phase states. Addenda now identify which MOLA results are historical and which later HiRISE run is current. No mock candidate generator or fabricated result path was found in the product workflow.
- The exact corrected files are listed in section H; **no further source-code correction is outstanding** after the final test rerun. Remaining recommendations concern data resolution, independent reference availability and operator deployment setup.

## A. Verified working features

- Phase 1: independent frontend/backend scaffold, strict pinned environments, CI checks, migrations, health endpoint, structured errors and logging.
- Phase 2: checksum-verified MOLA, HiRISE and Copernicus source ingestion/metadata. Product-specific adapters are separate from common raster validation. Raw DEMs and derived data remain outside Git.
- Phase 3: per-body metric coordinate transformations, unequal spatial supports, conservative target spacing, area averaging, separate valid coverage and honest `null` paired coverage where cell indices cannot be paired geographically.
- Phase 4: six requested feature categories are emitted independently: slope, local relief, elevation-dispersion roughness, profile/plan curvature, TPI and relative-position morphology. Synthetic reference surfaces and actual HiRISE/Copernicus feature rasters are present.
- Phase 5: configurable window generation, distribution distances, provisional mission weights, per-source coverage gates, clustering, progress, uncertainty caveats and reproducible report digests. Actual bounded search below produced ranked candidates.
- Phase 6: an actual Copernicus candidate became a GLB terrain mesh with geographic metadata and NoData-safe geometry; browser rendered it. Independent validation remains honestly unavailable.
- Phase 7: deterministic evidence-linked assessment, versioned passport, JSON/PDF export, and an actual ranked candidate passport.
- Phase 8: API/UI/database job integration, restart state, production Compose configuration and an actual browser workflow.
- Current validation: backend 104 passed/2 skipped in the default suite; database-enabled suite 106 passed; Ruff and formatting pass; mypy passes on 61 source files; frontend 14 tests pass, lint/typecheck/build pass; live Playwright 2/2 pass; npm audit reports zero vulnerabilities; pip-audit found no known third-party vulnerabilities (the local TerraTwin package itself is not published to PyPI and therefore cannot be audited by that tool).

## B. Partial implementations and scope limits

- **MEDIUM:** search covers a selected 10 km × 10 km Earth support around one available Copernicus tile. It is not a global Earth scan and does not establish novelty.
- **HIGH scientific-use limitation:** nominal common grid posting is about 30.746 m. Effective spatial resolution and source measurement uncertainty are undocumented for these products. The roughly 92 m 3×3 support derivatives do not resolve rover-scale obstacles or establish vehicle safety, wheel traction, soil mechanics, or operational mobility. Results support broad terrain-morphology comparison only; do not use them as rover hazard qualification.
- **MEDIUM:** Copernicus is a DSM and may contain buildings/vegetation. The candidate region's surface type is not bare-earth ground truth.
- **MEDIUM:** HiRISE DTM geometry is visualization-ready. It has not been compared with an independent elevation reference; the mesh status and passport say `UNVALIDATED`, with metrics absent. This is explicitly allowed when no suitable independent reference is available.
- **MEDIUM:** pixel-bootstrap standard errors describe only the implemented resampling variability. They are not confidence intervals and do not include spatial autocorrelation, instrument/DEM error or cross-feature dependence.
- **MEDIUM:** mission weights are versioned and inspectable, but remain researcher-selected provisional values.
- **LOW:** Moon is unavailable until a documented LOLA raster is supplied/registered. NASADEM/SRTM is not silently substituted.
- **MEDIUM deployment constraint:** production Compose targets one controlled tenant and one backend worker. It does not provide per-user identity, role-based access, rate limiting, multi-replica job leases, or a completed backup-restore drill.

## C. Failed tests and audit defects found

All findings below were fixed and the affected checks rerun.

1. **HIGH — Path containment used string-prefix comparison.** A sibling such as `raw_backup` could share the `raw` prefix. Replaced the comparison with `Path.is_relative_to()` and added a sibling-prefix traversal regression test.
2. **HIGH — Candidate-specific assessment and Terrain Twin creation searched only the newest discovery report.** Older persisted candidates became inaccessible after a newer run. Added exact candidate-to-report resolution across completed immutable runs and tests; manually verified candidate `eae3156598054eeb89b16f48` from run `7198b690a42a8ee4831b` still returns comparison, assessment, passport and Terrain Twin after later MOLA runs.
3. **MEDIUM — Caddy production route sent `/docs` to a nonexistent root docs path.** Changed proxy matching to `/api/*`, which includes the actual versioned docs URL. Rebuilt and verified `/api/v1/docs` and `/api/v1/openapi.json`.
4. **MEDIUM — The existing Playwright check assumed exactly one Mars dataset and could accept a previously visible job without proving submission.** Updated the journey to assert the selected HiRISE option, capture the POST response, require a newly submitted job, confirm job identity survives reload, inspect the stored report's actual HiRISE provenance and require ranked candidates.
5. **LOW audit-command issue —** initial pip-audit smoke used an invalid requirements export containing the local editable project. That invocation failed before auditing; reran using the installed environment path. No known third-party vulnerabilities were reported; the local unpublished package is skipped by pip-audit.

Non-failing tool notices: Starlette emits a deprecation warning for its TestClient/httpx integration; Node/Playwright emits a `module.register()` deprecation and terminal color warning. They did not fail checks.

## D. Independent scientific review

### Current accepted live run

- Run: `a2070ff303aaf4cf075e`; engine `0.6.0`; reproducibility SHA-256 `a2070ff303aaf4cf075e4c4e6f21adfb8eb3e747641d6efa5b26814747a679b8`.
- Mars source: HiRISE stereo DTM `DTEEC_048842_1985_048908_1985_U01`, raw manifest/checksum ID `9e723a990ef2694474bbc2486039098c885d09b938e70b903d60c15cbf704008`; source file checksum and manifest agree. The source is PDS IMG, metre elevations relative to Mars 2000 datum, nominal posting about 1.01 m; effective resolution is undocumented. NASA product record: [HiRISE DTM ESP_048842_1985](https://www.uahirise.org/dtm/dtm.php?ID=ESP_048842_1985); [official PDS DTM documentation](https://www.uahirise.org/pdf/HiRISE_RDR_v13_DTM.pdf); [source PDS IMG](https://www.uahirise.org/PDS/DTM/ESP/ORB_048800_048899/ESP_048842_1985_ESP_048908_1985/DTEEC_048842_1985_048908_1985_U01.IMG).
- Earth source: Copernicus DEM GLO-30 Public DSM tile `COP-DEM-GLO30-18-77`, ID/checksum `51587b0a9af347ff0bfe95b51ccd4d145ffdf0f74fdf18ce0213028f8041d989`; 3,600 × 3,600, 1 arc-second, EPSG:4326, metres relative to EGM2008; DSM, not bare-earth terrain.
- Earth search boundary (WGS84 west/south/east/north): `[77.45253008461685, 18.454716171043245, 77.54746991538315, 18.545277668852417]`.
- Configured Earth processing support: 10,000 m × 10,000 m; actual snapped support 10,023.247 m × 10,023.247 m, 326 × 326 cells. Mars reference support: configured 2,000 m × 2,000 m; actual 2,029.246 m × 2,029.246 m, 66 × 66 cells. Comparison posting 30.7461555 m, set by the coarser local Earth sample spacing; HiRISE is aggregated, not upsampled. Earth and Mars output grids represent different geographic supports, so there is no paired cell mask or paired area.
- Input source coverage: Mars 4,356/4,356 output cells; Earth 106,276/106,276. Terrain derivative outputs have 4,096 valid Mars samples after full-stencil edge exclusion, or 94.0312%; Earth source/feature support is also reported by its per-feature map. Coverage is recorded per feature in the run.
- 25 windows were generated/evaluated; 25 passed the configured evidence gates and were ranked after duplicate clustering. This is a bounded search result, not a global Earth analogue inventory.
- Rank 1: candidate `2c36fc1941cc6e7bf528b0e5`, centroid `77.51892474220436°E, 18.49999905383989°N`, window 2,029.246 m square, evidence coverage 0.9403122, weighted distance 0.11906692734805222, reported bootstrap standard error 0.006297975805193287. “Eligible” means only that it passed this run's configured provisional profile and coverage gates.

### Independent manual calculations

1. Small distribution case: reference `[0,0,0,0]`, candidate `[2,2,2,2]`. The first Wasserstein distance is exactly 2; both reference IQRs are 0, so the documented 1-degree slope normalization floor applies; normalized distance is exactly 2. The implementation test reports 2.
2. Actual rank-1 aggregation: independently evaluated `sum(weight_i × normalized_distance_i) / sum(weight_i)` from the stored JSON feature distances and profile weights. Result `0.11906692734805222`, exactly the reported weighted distance to floating-point precision (absolute difference 0.0 in the audit script).
3. Synthetic ScaleBridge and Terrain Analytics tests include flat/gradient surfaces, Gaussian hill/bowl, sinusoidal terrain, NoData, edge stencils, mismatched posting, curvature signs and independent calculation checks. Rasterio/GDAL reopen the actual input/output rasters.

### Current candidate feature comparison

Distances below are normalized first-Wasserstein distances under this run's configured scale floors. They are not percentages or universal suitability measures.

| Feature | Units | Mars median | Earth rank-1 median | Normalized distance |
|---|---:|---:|---:|---:|
| Slope | degree | 1.83274 | 1.76341 | 0.10990 |
| Local relief | m | 2.59167 | 2.48590 | 0.12562 |
| Elevation-dispersion roughness | m | 0.84294 | 0.79443 | 0.12606 |
| Profile curvature | m⁻¹ | 4.28496×10⁻⁵ | 1.88800×10⁻⁵ | 0.14854 |
| Plan curvature | m⁻¹ | −5.41010×10⁻⁴ | 8.79094×10⁻⁴ | 0.18807 |
| TPI | m | −0.01961 | −0.00481 | 0.03972 |
| Relative-position morphology | dimensionless | categorical distribution | categorical distribution | 0.08280 |

### Terrain Twin and assessment

- Twin ID `00f5f757604e98189edd7391`, candidate `2c36fc1941cc6e7bf528b0e5`, run `a2070ff303aaf4cf075e`.
- Source vertical units/reference are retained as metres/EGM2008 orthometric height. Mesh CRS is EPSG:32643; horizontal mesh posting is about 30.746 m; vertical exaggeration is 1.0. Mesh has 4,692 vertices; candidate crop 67 × 70 and mesh grid 68 × 69. Invalid cells are left out of triangles. The API served GLB, elevation map and slope map successfully.
- Independent metric validation: unavailable; status `UNVALIDATED`, reason “No independent reference DEM was selected.” Validation metrics are null. No same-source comparison is represented as independent validation.
- Deterministic assessment and passport tie claims to the actual measurements and retain limitations on soils, traction, dust/material, gravity, atmosphere and radiation. Passport `87a6d9aaa929fa46805523d0` is saved under ignored runtime storage at `data/results/evidence_passports/87a6d9aaa929fa46805523d0/`; JSON and PDF were generated from the API. Reproducibility SHA-256 `87a6d9aaa929fa46805523d0a6616afc469e11ef84ebd5129a40fe03ce359759`.

## E. Performance and resource observations

- A previous bounded 50 km Earth / 2 km Mars-support search, with 676 windows and 30 bootstrap replicates, completed in approximately 71 seconds in this local environment. A former 100-replicate benchmark took about 228 seconds for the same general window workload; that old run is not used for the current uncertainty result.
- The audited 10 km bounded search generated 25 windows and completed through the live browser journey in about 12 seconds, including API orchestration and page reload; this is one local observation, not a controlled performance benchmark.
- A previous Terrain Twin small-candidate engine run took 0.531 s and about 210,316 KiB peak RSS; the current mesh artifact has 4,692 vertices. This does not establish large-raster throughput.
- API smoke verifies health, docs, JSON and product pages but no statistically valid load/soak test or large-area memory profile has been run. Do not claim global scalability or high-concurrency job capacity.

## F. Security review

- Public request inputs use Pydantic bounds; file uploads are streamed with size limits, filename restrictions and validated raster metadata. Product sources resolve by manifest ID/checksum; API responses avoid raw filesystem paths.
- The path helper's shared-prefix escape was corrected and has a regression test. Source and candidate artifacts are verified against checksums before processing.
- Development Compose publishes service ports to loopback. Production Compose exposes only the Caddy proxy; database, API and Next.js are on an internal Compose network. Production web and API routes require Basic Auth; the smoke test observed HTTP 401 without credentials and HTTP 200 with the temporary smoke credential over HTTPS.
- Production secrets are environment-provided; `.env.production.example` contains placeholders. Production smoke used temporary credentials and removed the isolated Compose stack and temporary data afterward.
- `npm audit --audit-level=moderate`: 0 vulnerabilities. `pip-audit --path .../site-packages`: no known third-party vulnerabilities; TerraTwin's local package is skipped because it is not on PyPI. This is not a complete container/base-image SBOM scan.
- Remaining MEDIUM limitation: shared single-tenant Basic Auth, no per-user authorization/rate limiting, no multi-replica worker lease, and no restore drill. Use a private/trusted network or add an organization identity proxy before broadly exposing the service.

## G. Documentation review

Architecture, scientific methodology, dataset, API, validation and deployment documents exist. Older Phase 2/5/6/7/8 reports contain historically correct MOLA-era results that are superseded for the final workflow by this audit's HiRISE run. Addenda have been appended to identify the newer run and avoid treating old zero-ranked MOLA runs as current product status. The older runs remain useful evidence of honest insufficient-data handling.

## H. Exact files changed or corrected during this audit

- `backend/app/core/security.py`, `backend/tests/unit/test_security.py`: path containment fix and sibling-prefix regression test.
- `backend/app/services/discovery_results.py`, `backend/app/services/assessment_service.py`, `backend/app/api/routes/terrain.py`, `backend/app/api/routes/terrain_twin.py`, `backend/tests/unit/test_discovery_results.py`: share one persisted candidate-to-run resolver instead of duplicate/latest-only lookups.
- `deployment/Caddyfile`: corrected routing of the actual versioned API/docs paths.
- `frontend/tests/e2e/product-journey.spec.ts`: assert HiRISE selection, new job submission, job identity across reload and actual ranked report provenance.
- `documentation/validation/independent-phase-audit.md` and phase report addenda: independent findings and final acceptance evidence.

## I. Fixes completed and remaining actions

Completed: path containment regression, stored-run candidate resolution, Caddy API/docs routing, brittle/weak E2E assertions, current HiRISE user journey, real rank-1 mesh/assessment/passport generation and production Compose smoke test.

Before an external deployment, an operator still needs to provide a domain/host and provision the persistent `TERRATWIN_DATA_DIR` and database backup destination. Keep the API single-instance unless durable cross-process job claiming is added. For any mission-scale rover-mobility interpretation, acquire and validate higher-resolution Earth and planetary DTMs with documented effective resolutions and uncertainties. For metric reconstruction-validation claims, acquire a genuinely independent, vertical-datum-compatible DEM.

## J. Phase-by-phase acceptance decisions

### Phase 1 — Foundation

- **A Verified:** independent runtimes, app shells, health, migrations, quality checks and Docker development stack.
- **B Partial:** CI configuration has only local validation in this audit; no remote CI execution evidence.
- **C Failed tests:** none in the foundation report; current integration suite passes.
- **D Scientific:** no scientific output was claimed in Phase 1.
- **E Performance:** no foundation performance claim.
- **F Security:** development ports loopback-bound; production deployment wrapper added later.
- **G Docs:** architecture and development roadmap are present.
- **H Files:** root Compose/README/workflow, backend app/core/database, frontend app shell, Phase 1 docs.
- **I Fixes:** no unresolved Phase 1 code correction found in this audit.
- **J Decision:** **PASS** for the foundation scope.

### Phase 2 — Data ingestion

- **A Verified:** actual MOLA, HiRISE and Copernicus rasters; metadata, checksum and GDAL/Rasterio readability.
- **B Partial:** LOLA and NASADEM/SRTM product-specific acquisition remain unavailable/deferred; local supported raster ingest exists.
- **C Failed tests:** none in current full test suite. Failed-download, incomplete-download, invalid-CRS and checksum paths are covered by tests.
- **D Scientific:** native CRS, units, vertical references and effective-resolution unknowns are preserved; MOLA is not treated as direct observations where its source interpolates bins.
- **E Performance:** HiRISE source file is about 411 MB; bounded regional reads avoid treating the full file as a small sample.
- **F Security:** upload and source paths are constrained; path-prefix issue fixed.
- **G Docs:** exact products and citations in Phase 2 report plus this audit addendum.
- **H Files:** `backend/app/engines/data_ingestion/`, `backend/app/services/dataset_service.py`, `backend/app/api/routes/datasets.py`, manifests and `documentation/validation/phase-2-report.md`.
- **I Fixes:** recorded HiRISE product metadata and source checksum; no silent product substitution.
- **J Decision:** **PASS** for current MOLA/HiRISE/Copernicus ingestion; Moon coverage is explicitly unavailable.

### Phase 3 — ScaleBridge

- **A Verified:** coordinate transforms, metric grids, aggregation, NoData and independent vertical centering are callable and integrated.
- **B Partial:** absolute Mars/Earth heights are intentionally not reconciled; this is morphology comparison, not absolute elevation comparison.
- **C Failed tests:** an earlier unequal-support body-coverage denominator/common-mask issue was found in audit work and corrected; regression coverage now checks it. Current tests pass.
- **D Scientific:** target posting 30.746 m for current run, conservatively selected from Earth local spacing. Separate 2.029 km Mars and 10.023 km Earth supports use separate coverage; common paired coverage is null.
- **E Performance:** output cell cap is enforced; no large-area throughput claim.
- **F Security:** checksum-verified manifest inputs and bounded path resolution.
- **G Docs:** ScaleBridge methodology/report and `scale-bridge-hardening.md`.
- **H Files:** `backend/app/engines/scale_bridge/engine.py`, schemas, `tests/scientific/test_scale_bridge.py`, run report `data/processed/scale_bridge/5307327b9e0163613f7e/report.json`.
- **I Fixes:** unequal body supports and coverage denominator correction are included and tested.
- **J Decision:** **PASS**, with effective resolution/measurement uncertainty limitations carried into outputs.

### Phase 4 — Terrain Analytics

- **A Verified:** all six feature categories, numeric summaries, per-feature GeoTIFFs, edge/NoData and actual HiRISE/Copernicus maps.
- **B Partial:** morphology is a single-scale relative-position class, not geology or a formal geomorphological taxonomy.
- **C Failed tests:** none unresolved; known analytical surfaces and independent reference calculations pass.
- **D Scientific:** current maps use 30.746 m posting and approximately 92.24 m full 3×3 support; effective sensor resolution remains unavailable. This is not rover-scale obstacle mapping.
- **E Performance:** Earth analytics map has 106,276 source cells for the current support; no global benchmark.
- **F Security:** bounded processing is validated through manifest inputs and workspace paths.
- **G Docs:** terrain analytics methodology and Phase 4 historical report; current outputs `1e842c2956e29eb78c7e` (Mars), `53de3ba4f905c64e1852` (Earth).
- **H Files:** `backend/app/engines/terrain_analytics/engine.py`, schema, scientific tests and current derived maps.
- **I Fixes:** no unresolved algorithm correction; edge samples are missing by explicit full-stencil policy.
- **J Decision:** **PASS** for mapped, scale-qualified terrain morphology; not a rover hazard-resolution claim.

### Phase 5 — Analogue Discovery

- **A Verified:** actual run `a2070ff303aaf4cf075e`, 25 evaluated and 25 ranked windows; actual top candidate and feature distributions.
- **B Partial:** one 10 km area only; no global-search or novelty claim.
- **C Failed tests:** previous test's assumption of exactly one source and acceptance of a preexisting job were corrected; final E2E explicitly observes a fresh HiRISE submission and ranked results.
- **D Scientific:** manual weighted-distance calculation exactly matches the persisted run. Coverage, provisional weights, feature differences and bootstrap limitations are reported.
- **E Performance:** 25-window browser workflow about 12 seconds locally; 676-window run about 71 seconds in prior observation; neither is a general benchmark.
- **F Security:** bounded search dimensions/cell work, manifest IDs/checksums; path traversal regression fixed.
- **G Docs:** discovery methodology and full run report, including warning that ranking is not universal suitability.
- **H Files:** `backend/app/engines/analogue_discovery/engine.py`, mission profile config, job/service/routes, scientific tests and `data/results/analogue_discovery/a2070ff303aaf4cf075e/report.json`.
- **I Fixes:** exact uncertainty implementation remains labeled as pixel-bootstrap variability and warns of omitted spatial and source uncertainty.
- **J Decision:** **PASS** for reproducible bounded discovery under provisional profile; resolution limits restrict operational interpretation.

### Phase 6 — Terrain Twin

- **A Verified:** current rank-1 Earth candidate generated GLB, map previews and browser rendering; NaN/NoData geometry handling verified.
- **B Partial:** no suitable independent reference is ingested, so there are no accuracy metrics.
- **C Failed tests:** previous tests cover manual metrics and rejection of same-source/datum mismatch; current tests pass.
- **D Scientific:** units/EGM2008 reference preserved, EPSG:32643 horizontal mesh, 1× vertical scale; status explicitly `UNVALIDATED`.
- **E Performance:** current mesh has 4,692 vertices; earlier small-run timing/RSS is recorded, not generalized.
- **F Security:** candidate and source manifest resolution/checksum checks; older candidate report lookup is now run-aware.
- **G Docs:** Terrain Twin methodology and API docs state no metric-validation claim.
- **H Files:** `backend/app/engines/terrain_twin/engine.py`, `backend/app/engines/validation/engine.py`, API/viewer, `data/derived/terrain_twins/00f5f757604e98189edd7391/`.
- **I Fixes:** no invented validation; audit fixed historical-candidate lookup.
- **J Decision:** **PASS with explicit `UNVALIDATED` state**, as allowed by the phase instruction when no independent reference exists.

### Phase 7 — Terrain-to-Test Intelligence

- **A Verified:** actual rank-1 candidate assessment and passport `87a6d9aaa929fa46805523d0`; JSON and PDF exports generated and opened.
- **B Partial:** soil/material and planetary environmental parameters remain unsupported and are labeled missing/non-reproducible.
- **C Failed tests:** older-candidate assessment lookup was an actual API failure after newer runs; fixed by report-aware lookup and verified against runs `7198...` and `a207...`.
- **D Scientific:** conclusions are deterministic and tied to actual report records; no model-generated scientific facts. Transferability does not guarantee vehicle safety/performance.
- **E Performance:** passport JSON is about 60 KB and PDF about 16 KB in current run; generation not a material bottleneck in single-run checks.
- **F Security:** export uses validated passport data; user-supplied path is not exposed.
- **G Docs:** evidence schema, assessment methodology, PDF and API documentation.
- **H Files:** `backend/app/services/assessment_service.py`, `evidence_service.py`, `evidence_pdf.py`, schema/routes and frontend report.
- **I Fixes:** source-run resolution fixed; paired ScaleBridge coverage may be null and is preserved as null.
- **J Decision:** **PASS** for transparent evidence-report generation; missing soil and independent validation remain visible.

### Phase 8 — Product Integration

- **A Verified:** tested browser path selected Mars/HiRISE and Earth/Copernicus, submitted job, reloaded same ID, verified HiRISE provenance and 25 ranked candidates, opened comparison/passport, rendered mesh and checked `UNVALIDATED`; JSON/PDF API exports succeed.
- **B Partial:** single-worker/single-tenant deployment; no global search, multi-replica scheduler or independent DEM validation.
- **C Failed tests:** initial test could silently rely on an earlier job and assumed only one dataset. It now requires fresh POST response, HiRISE and nonzero ranked results. Caddy docs route mismatch fixed.
- **D Scientific:** outputs remain tied to checksummed data and explicit scale; the live Earth support is narrowly bounded and does not substantiate worldwide discovery or rover-scale operation.
- **E Performance:** local smoke timings are not load test results; concurrency/resource exhaustion and backup restore remain untested.
- **F Security:** isolated production smoke confirms TLS endpoint, protected route behavior and internal-only services. Shared Basic Auth is a deployment constraint.
- **G Docs:** production Compose, secret template, single-tenant constraints and backup guidance; actual external target not yet configured.
- **H Files:** production Compose/Caddy, FastAPI integration, frontend product features, Phase 8 report and Playwright test.
- **I Fixes:** run-aware candidate association, protected API/docs route, stronger live test and actual latest run/passport evidence.
- **J Decision:** **PASS for local end-to-end integration and production Compose smoke. External deployment and public multi-user readiness are not certified.**

## Acceptance gate summary

| Gate | Audit result |
|---|---|
| Real Jezero planetary elevation data | Pass — HiRISE DTM, checksum recorded |
| Real Earth elevation data | Pass — Copernicus GLO-30 DSM, checksum recorded |
| Explicit coordinate/resolution/vertical handling | Pass, with unknown effective resolution disclosed |
| Terrain maps/features | Pass for broad morphology at ~30.7 m grid posting |
| Actual ranked bounded candidates | Pass — 25 eligible/ranked in actual 10 km support |
| Terrain Twin rendered | Pass — real DEM-derived GLB in browser |
| Independent reconstruction validation | Unavailable; explicitly `UNVALIDATED`, no metrics |
| Experiment assessment and passport | Pass — actual candidate, versioned JSON/PDF |
| Reproducible provenance | Pass — checksums, run IDs and digests stored |
| Production stack locally started | Pass — migration, HTTPS proxy, authentication, health, PostGIS |
| External server deployment | Not performed; target infrastructure not provided |

## Overall acceptance decision

**Scientific and application acceptance: PASS with bounded-use limitations.** TerraTwin demonstrably executes its full Mars-to-Earth terrain morphology workflow using real data and produces a reproducible, evidence-linked ranked result. The candidate is not a claim of global novelty, guaranteed analogue quality, bare-earth truth or rover-scale navigability. The mesh is not independently metric-validated.

**Production deployment decision: READY FOR A CONTROLLED SINGLE-TENANT PILOT, NOT YET DEPLOYED.** Use the documented Compose setup only with a real domain, strong secret values, protected network access, persistent data storage and an operator-managed database backup. A public multi-user service needs an identity provider/access proxy, rate/resource controls and a backup/restore drill before public exposure. There are no unresolved Critical/High software defects in the tested single-instance configuration; the **HIGH scientific-use limitation** still bars rover-scale operational interpretation until finer, uncertainty-characterized terrain sources are added.
