# TerraTwin data flow

## Mission and source selection

1. Frontend reads `/api/v1/missions` and `/api/v1/datasets`.
2. Backend returns installed profiles and manifests with file availability and
   source checksum verification. It does not expose storage paths.
3. User selects a planetary source/reference, Earth source/search center, and
   physical support/window settings. A local GeoTIFF is streamed to a private
   staging file; ingestion validates and content-addresses it before creating
   a manifest.

## Processing job

1. `POST /api/v1/discovery/jobs` validates manifest IDs, geographic centers,
   dimensions and coverage/resource bounds; a fingerprinted job is persisted.
2. Worker resolves files under configured data directories and verifies raw
   raster checksums and any detached PDS label checksum.
3. ScaleBridge projects each body separately to local metric grids, selects a
   compatible cell scale, aggregates without claiming added information,
   propagates missing data, computes support coverage and writes relative
   elevation artifacts and a provenance report.
4. Terrain Analytics calculates supported feature rasters and numerical
   distributions for both paired support grids.
5. Analogue Discovery generates physically sized Earth windows, compares
   feature distributions under the versioned mission profile, and applies
   evidence/coverage gates before ranking. Candidates with incomplete required
   evidence remain unranked.
6. Artifacts are staged per job. On full success, completed processing
   directories are atomically moved to canonical stores and the candidate
   report is published last. Failure state is persisted; temporary staging is
   removed.

## Product read path

The browser polls durable job state and loads actual candidate/report JSON.
Comparison views request backend-generated previews cropped to the selected
planetary reference window and Earth candidate window. Image display stretch is
metadata for visualization, not a new measurement. Terrain Twin builds a mesh
from the verified candidate's source DEM. Independent validation is reported
only when a different suitable elevation dataset exists. Assessment and
Evidence Passport values resolve to the stored discovery, source and optional
mesh records; PDF/JSON exports preserve reproducibility and limitations.

## Scientific boundaries

The Mars and Earth arrays do not share geographic coordinates. Their aligned
array indices represent comparable physical support only. Absolute elevations
are not compared across planetary bodies. Relative terrain features, source
resolution, vertical metadata, NoData and uncertainty remain explicit. The
current local Earth source covers one Copernicus GLO-30 tile, so any current
candidate search is bounded to that raster and configured center.
