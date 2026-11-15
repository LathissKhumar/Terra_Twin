# Terrain Twin subsystem architecture

## Components

- `api/routes/terrain_twin.py` resolves candidate IDs from the newest discovery
  report, verifies the selected source against its manifest/checksum, validates
  bounded render options, and serves only known artifact names.
- `engines/terrain_twin/engine.py` owns polygon cropping, local metric grid
  creation, NoData-safe triangulation, normals, GLB output, preview images,
  metadata, resource caps, and deterministic output IDs.
- `engines/validation/engine.py` independently aligns a compatible second DEM,
  applies common-support masks and computes error metrics; it rejects duplicate
  source hashes and datum/unit mismatches.
- `domain/schemas/terrain_twin.py` defines request, candidate, metadata and
  validation contracts.
- `features/terrain-twin/terrain-twin-workbench.tsx` calls the backend and
  presents candidate status, validation, source metadata and artifacts.
- `features/terrain-twin/terrain-mesh-viewer.tsx` loads the backend GLB in
  Three.js and manages WebGL resources and camera controls.

## Request and artifact flow

`GET /api/v1/terrain-twins/candidates` lists actual rows from the latest
discovery report. `POST /api/v1/terrain-twins/candidates/{candidate_id}` accepts
only mesh limits and exaggeration; it does not accept a path. The route resolves
the raw Earth raster by checksum-addressed manifest under configured `data/`,
then invokes the engine. The engine writes derived files to
`data/derived/terrain_twins/<twin-id>/`. The response contains metadata and
allowlisted URLs for GLB, elevation, slope, error, and comparison-mask assets.
`GET /api/v1/terrain-twins/{twin_id}` returns the persisted metadata.

An independent reference is optional. When supplied by a dataset ID, it is
resolved through the same manifest and raw-directory rules. If compatibility
checks fail, reconstruction still returns but its validation status remains
`unvalidated`, with reason and no metrics.

## Resource and trust boundaries

The application resolves candidates from stored discovery outputs, verifies
their Earth source checksum, limits crop/output cells and vertices, and uses
an explicit artifact allowlist. Raw source files are never modified. GLB
construction is bounded and synchronous in FastAPI's worker pool. Mesh
resolution reductions are explicit stride sampling; they are not described as
new source information. Candidate discovery eligibility is preserved through
the UI and export metadata.

Scientific details and output values are documented in
[the Terrain Twin method](../scientific-methodology/terrain-twin.md).
