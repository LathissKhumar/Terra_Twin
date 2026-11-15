# Phase 8 API integration

All endpoints are rooted at `/api/v1`. FastAPI OpenAPI is served at
`/api/v1/docs`.

## Mission and datasets

- `GET /missions`: available profiles, planetary reference regions and source
  availability. Moon reference choices are data-driven.
- `GET /datasets?target_body=earth`: manifests with file availability and raw
  checksum verification.
- `GET /datasets/{dataset_id}`: validated source manifest.
- `POST /datasets/upload?target_body=...&vertical_units=...&vertical_reference=...&provider=...&product=...&attribution=...`:
  stream a raw GeoTIFF body with `X-Filename`. Only plain `.tif`/`.tiff` names
  are accepted; server-side size, CRS, raster and unit validation applies.
- `POST /datasets/acquire/mola-jezero`: configured official MOLA regional
  acquisition.
- `POST /datasets/acquire/copernicus-glo30?latitude=...&longitude=...`:
  acquire a specific public one-degree tile.

## Discovery jobs

- `POST /discovery/jobs`: submit a bounded job. Body requires planetary and
  Earth manifest IDs and centers (`longitude`, `latitude` in degrees). Optional
  fields declare support width/height, target resolution, candidate width,
  height and stride in metres, coverage thresholds, sample floor and maximum
  candidates. Returns `202` for a new job or `200` if an identical active or
  successful job is reused.
- `GET /discovery/jobs?limit=20&offset=0`: recent durable jobs.
- `GET /discovery/jobs/{job_id}`: lifecycle, stage, progress, result ID and
  sanitized failure information.
- `GET /discovery/jobs/{job_id}/candidates?minimum_coverage=0&limit=100&offset=0`:
  actual candidate report page and the searched WGS84 boundary. Candidates
  failing scientific evidence gates are included as unranked unless the
  requested display filter excludes them.
- `GET /discovery/jobs/{job_id}/report`: complete validated engine report.

## Candidate and comparison

- `GET /terrain/candidates/{candidate_id}`: candidate plus discovery provenance.
- `GET /terrain/candidates/{candidate_id}/comparison`: feature comparisons,
  coverage, resolution and preview URLs.
- `GET /terrain/discovery-runs/{run_id}/features/{mars|earth}/{feature}/preview/{candidate_id}`:
  PNG visualization cropped to the actual planetary reference window or Earth
  candidate. Pixel colors use a visualization stretch; source feature values
  remain in the JSON report.
- Existing candidate APIs: `/terrain-twins`, `/assessments` and
  `/evidence-passport`; PDF/JSON exports retain source and processing records.

## Errors and limits

Input validation returns `422`; malformed or absent IDs return `404`; a
candidate request on a noncompleted job returns `409`; capacity exhaustion
returns `429` with `Retry-After`; unavailable database or stored artifacts
return `503`. Error JSON uses `error.type`, `error.message`, `error.details` and
`error.path` for HTTP and validation errors. Internal exception text and
filesystem paths are not returned.

Maximum request dimensions/candidate counts are encoded in Pydantic schemas.
The source upload limit is 2,000,000,000 bytes. The in-process worker processes
one job at a time and permits no more than two queued/running records.
