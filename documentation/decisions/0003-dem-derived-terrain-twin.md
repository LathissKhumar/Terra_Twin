# ADR 0003: DEM-derived, bounded GLB terrain twins

- **Status:** Accepted for Phase 6 implementation
- **Date:** 2026-11-15

## Context

TerraTwin must independently reconstruct a selected Earth candidate in 3D,
preserve its coordinate and elevation provenance, handle NoData holes, and
avoid claiming validation when an independent compatible reference is absent.
The current discovery outputs contain only insufficient-evidence windows and
the local Earth DEM collection contains no datum-compatible independent
reference.

## Decision

Generate chunked binary glTF 2.0 meshes directly from a checksummed candidate
DEM using Rasterio/GDAL, NumPy, and PyProj. Project to a local metric CRS; retain
source vertical units and datum; default to 1× exaggeration. Apply deterministic
stride sampling under an explicit vertex budget. Omit any triangle cell whose
footprint touches invalid data. Resolve sources only by candidate ID and
manifest, never by request-provided filesystem paths.

Treat validation as an independent-data comparison. Require a distinct source
checksum, metre units, and equal documented vertical-reference strings. Do not
silently convert datums. Return `unvalidated` and no metrics if a suitable
reference is unavailable or incompatible. The browser renders the actual GLB
with Three.js `GLTFLoader` and `OrbitControls`.

## Consequences

The current Phase 6 demonstration can prove real DEM-to-mesh processing and
browser visualization but cannot claim metric validation or analogue
suitability. The mesh is a visualization product; stride sampling and
display-only slope coloring do not replace terrain analysis. A later validated
vertical-datum transformation or suitable same-datum reference source can
enable independent comparison without changing this trust contract.

See [Terrain Twin methodology](../scientific-methodology/terrain-twin.md) and
[Phase 6 validation report](../validation/phase-6-report.md).
