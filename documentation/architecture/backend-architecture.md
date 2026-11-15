# Backend architecture

The backend is a FastAPI modular monolith. Public routes live under
`/api/v1`; Pydantic schemas define API and scientific-engine boundaries.
Routes validate and serialize requests, services resolve provenance and
orchestrate work, and engines remain independently callable without FastAPI or
database dependencies.

## Runtime modules

- `api/routes/missions.py`: installed mission profiles and data-backed
  planetary reference regions.
- `api/routes/datasets.py`: manifest catalog, validated source inspection,
  bounded streaming GeoTIFF ingestion, and configured MOLA/Copernicus
  acquisition.
- `api/routes/discovery.py`: durable job submission, status, report and
  paginated candidate retrieval.
- `api/routes/terrain.py`: candidate records, comparison metadata and cropped
  visualization-only feature map previews derived from stored rasters.
- `api/routes/terrain_twin.py`, `assessments.py`, `evidence.py`: DEM mesh,
  deterministic mission assessment and JSON/PDF evidence exports.
- `services/discovery_jobs.py`: validates manifest IDs/checksums, restores
  detached PDS label metadata, runs ScaleBridge → Terrain Analytics → analogue
  discovery in a single bounded worker, atomically publishes completed result
  directories, and records failures.
- `engines/`: independently callable scientific implementations and typed
  result reports.
- `domain/models/discovery_job.py`: durable lifecycle state and a partial
  unique index preventing duplicate active jobs for one request fingerprint.
- `migrations/versions/0002_discovery_jobs.py`: PostgreSQL job table and
  indexes.

## Job lifecycle

`POST /api/v1/discovery/jobs` accepts dataset manifest IDs, explicit planetary
and Earth centers, physical comparison support, candidate window/stride,
coverage gates and resource caps. The API stores a `queued` record and returns
without running raster work in the request. A one-thread executor processes
one job at a time; at most two jobs may be queued or running. Exact active or
successful configurations are reused. Failed requests can be resubmitted.
After a process restart, stale `running` jobs become `interrupted`, while
queued jobs resume. Results are made visible only when the final discovery
report has been published.

This runner is single-instance. A multi-replica deployment needs a database
lease/claim protocol before scaling API replicas. This release does not add a
distributed queue. Job failure messages are bounded and redact the configured
data root. Raw files are resolved by validated content-addressed manifest IDs;
the API accepts no arbitrary file path.

## API contract and errors

HTTP, validation and domain failures use structured `error` envelopes. The
health endpoint checks PostgreSQL and PostGIS. Long-running work is read through
`GET /api/v1/discovery/jobs/{job_id}`; source and job IDs are opaque identifiers.
Feature image responses are generated from actual analytics rasters and crop
the selected planetary/reference and Earth/candidate windows. Their display
stretch is for visualization only and is not a numerical product.

See [Phase 8 API routes](../api/phase-8.md) and OpenAPI at
`/api/v1/docs` when the service is running.
