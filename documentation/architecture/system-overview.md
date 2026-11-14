# TerraTwin system overview

## Implemented in Phase 1
TerraTwin is a modular monolith with a separate Next.js client. FastAPI exposes
root metadata and versioned service health. PostgreSQL/PostGIS is provisioned
through Compose and Alembic. Local data directories contain no scientific data.
The frontend displays live service readiness and an explicit no-data state.

## Target architecture (future phases)
Client -> versioned API -> application services -> independent scientific engines.
Services use repositories for PostgreSQL metadata, job state and Earth boundaries.
Artifacts reside under configured data storage; clients receive opaque IDs, never
arbitrary filesystem paths. Domain schemas define validated contracts. Engines
must not import FastAPI or database code.

The first scientific workflow is Jezero-to-Earth comparison for rover mobility
and navigation. Planetary reference coordinates must retain their planetary body,
CRS and longitude conventions; Earth footprints may use EPSG:4326. Mars
coordinates must never be stored as terrestrial WGS84 geometry.

No job runner, ingestion pipeline, feature extraction, ranking, mesh reconstruction,
validation or passport export is implemented. These are gated roadmap phases.
TerraTwin has no source, model, runtime or output dependency on another project.

## Data and scientific boundaries
Every future output must link source checksums, product versions, CRS, vertical
reference, units, effective resolution, parameters and processing history.
Absence of evidence is represented explicitly, never as zero measurements.
Terrain similarity cannot establish that a site is under-explored or suitable
for every planetary experiment. No source products are selected in Phase 1.

