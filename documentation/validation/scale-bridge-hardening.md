# ScaleBridge hardening addendum

## Scope

This addendum strengthens Phase 3 evidence handling around interpolated MOLA
MEGDR cells. It does not add terrain analytics, analogue discovery, or a trained
model.

## Product-specific quality mask

For the Jezero-coverage topography product MEGT44N000HB, ScaleBridge can accept
the co-gridded PDS companion MEGC44N000HB. The official label describes
COUNTS_PER_BIN, unsigned 8-bit samples, a 5,632 × 11,520 grid at 128
pixels/degree, and the same 0–44°N, 0–90°E tile bounds.

The mask policy is precise: a zero count excludes that MOLA bin; any positive
count allows its elevation value to participate. Count magnitude is not used
to weight elevations. This avoids treating counts as statistical weights for
MEGDR median values.

## Provenance and reproducibility

The ancillary manifest is isolated under data/manifests/ancillary/ so API
routes that enumerate elevation manifests do not misinterpret it as a DEM. It
contains checksums for the IMG and detached label, source product identifiers,
grid metadata, count semantics, and the parent topography manifest ID. Raw
count bytes are stored by SHA-256 and are not modified.

ScaleBridge validates ancillary checksum, parent ID, grid CRS, dimensions,
pixel resolution, bounds, data type, and exact affine transform. The report
identifies the counts product and mask policy. Ancillary manifest content is
included in the run reproducibility hash. Without counts, Mars runs contain an
explicit warning that interpolated bins cannot be separated from directly
observed bins.

## Commands

    uv run --directory backend python scripts/acquire_mola_observation_counts.py
    uv run --directory backend python scripts/run_scale_bridge_real.py +      --mars-center 77.5 18.4 --earth-center 77.5 18.5 +      --support-width-m 20000 --support-height-m 20000 +      --use-mola-observation-counts

## Scientific scope and limitations

The count raster supplies shot-presence evidence, not an error model. It cannot
recover individual altimeter measurements, quantify uncertainty, or determine
effective terrain resolution. The topography and counts are co-registered
product outputs, not independent validation data. This source mask reduces
support where bins have no observation but does not erase other product,
instrument, interpolation, or scale limitations.

## Models and training

ScaleBridge uses deterministic coordinate transforms, GDAL/Rasterio
area-averaging, valid-data masks, unit conversions and report construction. It
contains no machine-learning model and requires no model training. The count
product is measured ancillary data, not an inferred prediction.
