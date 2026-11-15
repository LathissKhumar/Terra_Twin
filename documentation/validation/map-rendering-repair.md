# Discovery map rendering repair

**Date:** 2026-11-15

## Cause

The discovery page restored a succeeded database job whose saved report used an
older schema, so candidate retrieval failed and the `CandidateMap` component
was never mounted. Once a current report was available, MapLibre GL JS v6 still
failed to load its webpack worker, leaving a blank canvas.

## Changes

- Configured MapLibre's worker using the package's worker module URL, emitted by
  Next.js as a same-origin asset.
- Added map `ResizeObserver` handling and a fitted camera for the actual
  returned geographic footprints.
- Added explicit map loading/error/empty states and the actual footprint count.
- Replaced the empty background-only map style with the OpenFreeMap Liberty
  basemap, enabled source attribution, and added a metric scale bar. The style
  URL is configurable at build time with `NEXT_PUBLIC_MAP_STYLE_URL`.
- Added a visible eligible/insufficient-evidence legend. The surrounding UI now
  says the basemap provides geographic context, rather than claiming that no
  basemap is present.
- Changed initial discovery restoration to try completed jobs newest-first and
  fall back when a historical report fails current-schema validation. The
  default Earth source now prefers a verified bare-earth DTM when available.
- Extended the live product journey to assert a visible canvas and click a
  candidate polygon to open its comparison page.
- Fixed the discovery-job pipeline to derive the landform class normalization
  from the planetary TPI feature report and apply that same scale to Earth
  analysis. This was necessary for a fresh, scientifically consistent job to
  complete under the current report schema.

## Demonstration

Fresh API job `f483def7-719c-4340-a404-fc320344f6c2` completed successfully
with HiRISE Jezero and the USGS Idaho bare-earth DEM. It generated and evaluated
25 candidate windows; all 25 were eligible and ranked under the configured
profile. The discovery page restored the job, displayed the actual returned
candidate polygons, and MapLibre rendered them in a 1,230 × 358 CSS-pixel
canvas. Chromium clicked the central footprint and navigated to that
  candidate's actual comparison page. Basemap geography is contextual only;
  candidate polygons remain sourced exclusively from the discovery API.

## Checks

- Map worker loading: no browser console or failed-request errors.
- Candidate map: one visible MapLibre canvas, candidate polygons visible, map
  loading overlay removed.
- Candidate interaction: clicking a footprint opened the corresponding
  `/candidates/<id>/comparison` route.
- Historical-job recovery: the frontend skipped a newer pre-schema report and
  restored valid completed job `f483def7-719c-4340-a404-fc320344f6c2`.
- Frontend production build uses `NEXT_PUBLIC_API_URL=http://localhost:8001/api/v1`.
- Follow-up map usability check: Chromium loaded the basemap attribution
  (`OpenFreeMap © OpenMapTiles Data from OpenStreetMap`), rendered the
  candidate polygons on top of real geographic context, showed a metric scale
  and category legend, and reported no failed browser requests. The map was
  captured and visually inspected after the frontend container rebuild.
