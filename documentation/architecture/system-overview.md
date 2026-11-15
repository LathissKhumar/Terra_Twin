# TerraTwin system overview

TerraTwin is an independently deployable geospatial modular monolith: a
Next.js App Router client, FastAPI application, PostgreSQL/PostGIS metadata and
job store, and independently callable Python scientific engines. It has no
runtime, source, model-checkpoint or output dependency on another project.

## Integrated path

The initial mission is rover mobility and terrain navigation with Jezero Crater
as a Mars reference. A user selects checksummed dataset manifests and explicit
body-specific geographic centers and physical support dimensions. A persisted
job runs ingestion checks, ScaleBridge, terrain analytics and candidate scoring
in sequence. Candidate reports and derived rasters are published only after
the complete processing chain succeeds. The client reads job status, candidate
records, comparison rasters, Terrain Twin artifacts and Evidence Passports from
versioned APIs.

The current local sources are the MOLA `MEGT44N000HB` regional tile and one
Copernicus DEM GLO-30 public DSM tile. This supports a bounded search within the
Earth raster's actual footprint. It is not global Earth discovery. Direct MOLA
observation support is sparse; candidates without required evidence remain
unranked. Lunar selection is exposed only when a validated lunar raster is
available; no LOLA acquisition is configured in this installation.

## Component responsibilities

- `backend/app/api`: request validation, structured errors, pagination and
  artifact delivery. Routes do not calculate terrain features.
- `backend/app/services`: manifest resolution, persistence and orchestration.
- `backend/app/engines`: independent ingestion, ScaleBridge, terrain analytics,
  analogue discovery, mesh generation, validation and assessment.
- PostgreSQL: durable discovery job state; raw and derived raster products stay
  in the configured data volume and are addressed through opaque IDs.
- `frontend/features`: mission/dataset selection, status polling, actual
  candidate map, raster comparison, mesh viewer and report UI. Browser code does
  not calculate scientific measurements.

## Scientific boundaries

Each dataset retains checksum, product, CRS, bounds, source/effective
resolution, vertical units/reference and processing history. Mars and Earth
are compared on separate local metric grids with relative elevation; shared
indices describe paired support and are not spatial intersections. Similarity
does not imply universal suitability. A mesh without a genuinely independent
reference is labeled `UNVALIDATED`.

See [backend architecture](backend-architecture.md),
[frontend architecture](frontend-architecture.md),
[data flow](data-flow.md), the [scientific methodology](../scientific-methodology/README.md),
and the [Phase 8 plan](phase-8-plan.md).
