# Frontend architecture

The frontend is a strict TypeScript Next.js App Router application. The root
layout provides accessible navigation and the dark scientific workspace. The
client does not compute terrain features, distances, coverage or rankings.

## Product routes

- `/missions`: data-backed Mars/Moon body and reference-region selection,
  dataset catalog, source provenance, explicit centers and GeoTIFF ingestion.
- `/discovery`: ScaleBridge and discovery configuration, durable job submission,
  refresh-safe status polling, coverage filter, actual ranked/unranked
  candidates and candidate footprints returned from the backend.
- `/terrain-comparison`: entry point to candidate-scoped comparison pages.
- `/candidates/[candidateId]/comparison`: backend-produced cropped terrain
  feature maps, distribution measurements, source resolution, coverage and
  limitations.
- `/terrain-twin`: existing Three.js mesh viewer with elevation/slope modes,
  wireframe, controls and validation state.
- `/candidates/[candidateId]/passport`: deterministic assessment and
  provenance report with JSON/PDF export.

Mission Explorer and Discovery share a workflow component so source selection,
configuration and job state are consistent. Stored job IDs are queried from the
API after refresh. MapLibre displays actual returned candidate polygons over a
real OpenFreeMap/OpenStreetMap basemap. Its attribution control is enabled; the
style URL can be set with the public build-time `NEXT_PUBLIC_MAP_STYLE_URL`.
Basemap styling is contextual only and is not a terrain-analysis input. Empty,
loading, tile-error and unavailable source states are explicit.

`lib/product-api.ts` is the versioned REST client and reads the build-time
`NEXT_PUBLIC_API_URL`; this variable is public and must not contain credentials.
Backend error envelopes are surfaced to the user. MapLibre and Three.js are
loaded only for their visualization modules. Evidence and mesh artifact URLs
are served by the API and retain source metadata.

Vitest covers UI states and errors; Playwright is used for browser checks.
Lint, typecheck, tests and production build are independent gates.
