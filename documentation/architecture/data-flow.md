# Data flow

## Implemented
1. Browser loads the Next.js foundation page independently of the backend.
2. HealthPanel fetches GET /api/v1/health with a five-second request limit.
3. FastAPI performs bounded PostgreSQL connectivity and PostGIS extension checks.
4. Backend validates HealthResponse and returns 200 or 503.
5. Browser validates the contract and displays readiness or an unavailable state.

Compose starts PostgreSQL, waits for its health check, runs the Alembic migration,
then starts the API. Frontend startup is independent of API readiness.
There is no scientific data movement or background processing in Phase 1.

## Planned scientific flow
Source raster + authoritative product metadata -> ingestion manifest ->
ScaleBridge -> terrain features -> bounded Earth-window comparison ->
candidate evidence -> DEM mesh + independent reference validation ->
experiment assessment -> JSON/PDF evidence passport.

Cross-body comparison means harmonizing physical sampling support, not spatially
intersecting Earth and Mars coordinates. Alignment/intersection applies within
each body's datasets or between independent references for the same Earth site.
Vertical datums must be explicit; absolute elevations across planets must not be
silently combined.

Distance uses weighted valid feature distances divided by valid contributing
weights. Feature normalization, minimum evidence, neighborhood scales and
uncertainty interpretation remain scientific design decisions for later phases.
No fixed 5% missing-data threshold is accepted yet.

No example manifest containing invented dataset IDs, checksums or acquisition
dates is provided as evidence. Real manifests will be generated from actual files.

