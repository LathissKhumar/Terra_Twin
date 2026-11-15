# Phase 8 integration plan and outcome

## Inspected baseline

Phase 1–7 engines and their reports existed, but mission/discovery/comparison
routes were not fully mounted, there was no persisted processing-job lifecycle,
and the frontend mainly exposed Terrain Twin and Passport pages. Runtime inputs
were a checksummed MOLA Jezero area product and one Copernicus GLO-30 Earth
tile; source coverage was therefore local, not global.

## Intended and implemented changes

- Mount mission, dataset, durable discovery, candidate and comparison routes in
  the versioned FastAPI application.
- Add a PostgreSQL `discovery_jobs` table and fingerprint-based duplicate
  control, a one-thread bounded worker, startup recovery, explicit failure
  states and staged atomic artifact publication.
- Resolve source data only by validated manifest IDs and verify raster/label
  checksums. Pass the official detached MOLA PDS label to the raster engine.
- Run existing ScaleBridge, Terrain Analytics and Analogue Discovery engines;
  do not reimplement their calculations in the API or browser.
- Add mission/source selection, explicit Earth and planetary centers, real
  source acquisition/GeoTIFF upload, physical search setup, refresh-safe job
  polling, actual candidate boundaries, coverage filtering and record links.
- Add candidate-scoped feature-map previews and display ScaleBridge CRS,
  resampling, resolution and valid-support metadata.
- Connect product navigation to the existing mesh, assessment and JSON/PDF
  Passport endpoints. Add UI loading, empty and backend error states.
- Add live API and component tests, deployment guidance and an integration
  report with actual run outputs and limitations.

## Observed integration findings

- The first live job exposed a missing detached-label handoff for MOLA. The
  source label and its manifest checksum are now resolved and validated by the
  worker.
- The next run exposed a mission profile path error. The runner now resolves
  the versioned profile from the backend package's configured tree.
- The completed actual job evaluated 16 windows and reported zero eligible or
  ranked candidates because planetary feature coverage was about 0.21%. The
  stored report marks every candidate insufficient evidence; it emits no
  weighted distance. This is an evidence limitation, not a missing job result.

## Remaining acceptance risks

- Single-thread processing is single-instance. It is not horizontally
  scalable without a database lease/claim mechanism.
- No authenticated user isolation, rate limiting, TLS gateway or production
  deployment profile is included; Compose binds local ports to loopback.
- Local planetary and Earth inputs do not support representative/global
  discovery. A full product acceptance claim requires broader data.
- Independent validation data for the selected candidate is unavailable; the
  generated DEM mesh is visualization-only and `UNVALIDATED`.
- Browser tests and restart/error simulations are recorded in the Phase 8
  validation report. The report distinguishes executed checks from load and
  deployment tests that remain outstanding.
