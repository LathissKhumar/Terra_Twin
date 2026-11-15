# ScaleBridge methodology (Phase 3)

## Purpose and comparison semantics

ScaleBridge places two validated elevation rasters on separate local metric
grids with equal cell dimensions and equal physical support. It does **not**
intersect Mars and Earth coordinates: those bodies have unrelated geographic
coordinate spaces. Paired array indices denote comparable-sized cells centered
on independently supplied planetary and Earth coordinates. The output is for
relative terrain morphology only; it does not imply that either site is an
analogue or that the two sites share absolute elevations.

The public engine is `run_scale_bridge` in
`backend/app/engines/scale_bridge/engine.py`. Inputs are raster paths, validated
`DatasetManifest` values, an optional detached-label path for PDS products,
body-specific longitude/latitude centers, requested support dimensions, and an
output directory. It verifies source checksums and raster metadata before
processing. `backend/scripts/run_scale_bridge_real.py` reproduces the acquired
MOLA-to-Copernicus verification using explicit centers and support dimensions.
Run it from the repository root with:

```sh
uv run --directory backend python scripts/run_scale_bridge_real.py \
  --mars-center 77.5 18.4 --earth-center 77.5 18.5 \
  --support-width-m 20000 --support-height-m 20000
```

## Coordinate handling

For each source independently, PyProj resolves its geodetic CRS and ellipsoid.
The engine creates a local azimuthal-equidistant CRS centered at the supplied
coordinate, using that body's ellipsoid. It transforms a neighboring source
pixel at the requested center into the local CRS to measure actual local ground
spacing in metres. This handles angular source coordinates without interpreting
degrees as distances and accounts for the MOLA simple-cylindrical east-west
scale at latitude. The source CRS and native bounds are retained, and bounds
are additionally transformed to geographic longitude/latitude for the report.

The planetary and terrestrial local CRSs remain separate. Both grids use a
centered affine transform with the same cell size and dimensions, but each
transform is expressed in its own local CRS. The `common_support_mask.npy` is a
pair-index mask and has no geographic CRS of its own; the per-source GeoTIFFs
carry their respective CRS and complete provenance tags.

## Resolution selection and resampling

Let `s_px` and `s_py` be local metric spacings measured from one source pixel in
the x and y directions. If authoritative product metadata provides an effective
resolution `s_eff`, that value is included. The minimum comparison cell size is:

```text
s_floor = max(s_px, s_py for both sources, documented s_eff for either source)
```

The default target is `s_floor`. A caller may request a desired target; if it is
finer than `s_floor`, the actual target remains at `s_floor` and the report
warns that no upsampling occurred. Support dimensions are explicit inputs, each
capped at 500 km; target dimensions use `ceil(support / target_cell_size)`, so
the reported actual support can slightly exceed the requested dimensions. The
output grid is capped at four million cells. If the desired target would exceed
that cap, the engine coarsens to the smallest target-cell size that satisfies
the cap and records that extra loss of detail in both the report and warnings.

Both elevation rasters are reprojected with Rasterio/GDAL `average` resampling
onto their respective local grids. A parallel warp of the source valid-data
indicator estimates the valid source fraction per output cell. An output cell is
valid only when that fraction meets the configured default threshold of 0.999.
This excludes partial edge cells and cells substantially intersecting NoData.
The common support is the logical AND of the two per-source masks. Missing
values remain NaN in memory and are encoded as the declared finite NoData value
in each derived GeoTIFF; the Boolean `.npy` mask is independent of CRS.

This is controlled aggregation. It does not claim that nominal posting equals
effective terrain resolution, and it never creates fine terrain detail by
upsampling. Product-specific effective resolution is used only when documented
in the manifest; otherwise the report says it is unavailable and treats local
pixel spacing as a conservative grid floor.

## Vertical treatment

Supported linear units (metres, kilometres, feet) are converted to metres. An
unrecognized unit is rejected. Each aggregated surface is independently
centered by subtracting its median over valid cells:

```text
z_relative = z_aggregated_in_metres - median(z_aggregated_in_metres over valid cells)
```

This removes absolute offsets for morphology processing; it is not a vertical
datum transformation. Source vertical units and reference remain in the report
and GeoTIFF tags. Different references, including Mars areoid-relative radial
topography and Earth EGM2008 orthometric height, are explicitly warned about.
Absolute elevation differences between the bodies are not produced.

## Provenance and reproducibility

The run identity is a SHA-256 over the two source manifest IDs and scientific
metadata, explicit centers, support, selected resolution, valid-fraction
threshold, unit conversion and processing-software versions. The report records
the full digest, native and geographic bounds, local CRSs, measured pixel
spacing, effective resolution when known, resolution decision, physical support,
resampling, coverage, limitations, software versions and output artifact
SHA-256 values. Raw files are read-only and must match their manifest checksums.

### MOLA direct-observation support

The selected MOLA MEGDR tile has an official companion product,
`MEGC44N000HB.IMG`, at the same 128 pixels/degree grid. Its PDS label identifies
an unsigned 8-bit `COUNTS_PER_BIN` image, one value per MEGDR bin. TerraTwin can
acquire this file explicitly with:

```sh
uv run --directory backend python scripts/acquire_mola_observation_counts.py
```

The ancillary manifest records its own checksum and label checksum, grid
metadata, observation-count semantics, observed-cell count, and the exact
topography manifest ID it accompanies. Raw bytes are preserved. The ScaleBridge
run accepts it as an optional `ObservationCountSource`; use
`--use-mola-observation-counts` in `run_scale_bridge_real.py` to request the
direct-observation mask. Before use, the engine checks provenance, checksum,
CRS, dimensions, resolution, bounds, data type and exact grid transform against
the MOLA raster.

Count zero means that bin has no direct MOLA observation and is excluded from
the valid-source mask. Positive count means only that at least one observation
supports the bin. Count magnitude is **not** an elevation weight: the MEGDR
cell value is a product-level median, and weighted combination of those medians
is not justified by this companion layer. The count filter participates in the
same source-valid-fraction threshold as raster NoData and is included in the
coverage, report and reproducibility digest. Omitting the layer remains
possible, but generates a warning that interpolated no-observation bins cannot
be distinguished.

This masks cells without direct shots; it does not turn MOLA into a uniformly
sampled terrain truth surface, quantify shot-level uncertainty, or establish
effective terrain resolution. The observation-count map itself is a documented
ancillary product rather than a trained model.

## Real product verification

The original Phase 3 baseline (without the optional observation-count raster) used the acquired MOLA
`MEGT44N000HB.IMG` tile and Copernicus GLO-30 tile
`Copernicus_DSM_COG_10_N18_00_E077_00_DEM`. Centers and support are explicit
parameters; this is a processing demonstration, not a candidate discovery.

| Measurement at supplied center | MOLA Jezero center (77.5°E, 18.4°N) | Copernicus Earth center (77.5°E, 18.5°N) |
|---|---:|---:|
| Source CRS horizontal units | metre | degree |
| Measured local pixel spacing x | 439.329 m | 29.334 m |
| Measured local pixel spacing y | 463.000 m | 30.746 m |
| Documented effective resolution | unavailable | unavailable |
| Vertical reference | GMM3 Mars areoid referenced radial topography | EGM2008 orthometric height |

For a requested 20,000 m square support, ScaleBridge selected 463.000 m cells,
aggregated Copernicus, and created 44 × 44 outputs with actual support
20,372 × 20,372 m. The real input rasters each had 100% valid coverage over
that support (1,936 output cells; common valid area 415,018,384 m²). This coverage
does not certify measurement accuracy or surface equivalence. Copernicus GLO-30
is a DSM including vegetation/buildings.

### Counts-enabled real run

On 2026-11-14, the official count tile was acquired, checked against the PDS
label and ingested. Its source raster SHA-256 is
cfb4d7e3626106ef4ed2a466eb03a538feed9c163be99e860b7ae8700a8ecab5; the PDS
label SHA-256 is
e7bde6960c05e9fc48ff6417ee3e2b12ed271af16ea85294a775a6948d890a1e. The image
contains 64,880,640 cells, of which 20,551,186 have positive counts, with a
maximum count of 14. It is explicitly linked to the ingested
MEGT44N000HB source manifest.

The same center, 20 km requested support and 463.000 m comparison cells were
run with the counts option. The 44 × 44 pair-support grid has 1,936 requested
output cells. After excluding zero-count MOLA bins and applying the configured
0.999 valid-source fraction, 211 cells remain valid on Mars. Earth retains
1,936 cells. Common support is therefore 211 / 1,936 = 10.90%, or 45,231,859 m²
using projected cell area. This limited footprint must accompany any downstream
comparison; it is not a similarity score or candidate ranking.

The reproducibility SHA-256 is
e2fe8955610bb112c46f36c63f1e368931969ae75c173586c5b4e49386fd9e36.
Artifact SHA-256 values: planetary relative raster
d384c3456337d7fa81da9b52cc2f1b6c4bb0aebdfd0ad6bec7d5b9ecdee3ab30;
Earth relative raster
ea6c73274f31cdb4ec145b613bc13b135141f2331738f20080db5322d0b69a73;
common-support mask
109ee797b9ea6c68a3b7b24b855c8d5651b6485b81819153d4a274421cb66fc7.

Official product sources:

- [NASA PDS MOLA MEGDR documentation](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html) describes MEGDR grids, pixel-per-degree products and companion counts maps.
- [Official MEGC44N000HB PDS label](https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/megc44n000hb.lbl) documents the 5,632 × 11,520 unsigned 8-bit counts image, its 128-pixel/degree grid and 0–44°N, 0–90°E coverage.
- [Official MEGC44N000HB counts image](https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/megc44n000hb.img) is the companion input described above. The selected topography is the PDS3 128-pixel/degree tile; nominal posting is not asserted to be effective terrain resolution.
- [Copernicus DEM product specifications](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM) document GLO-30 grid spacing and EGM2008 vertical reference.

## Limits

- No planetary/Earth global coordinate intersection is meaningful; centers and
  support are user-selected.
- Effective spatial resolution and source uncertainty remain unavailable for
  these manifests, so no uncertainty interval is fabricated.
- The two local supports may represent different physical locations and terrain
  contexts; the engine only guarantees stated dimensions and cell sizes.
- The default 0.999 valid-source fraction is an explicit engineering policy,
  not a claim that all retained cells have uniform measurement uncertainty.
- Relative median centering preserves local relief but does not harmonize
  datums, remove instrument biases, or make DSM and planetary topography
  observation methods equivalent.
- This phase does not compute slope, roughness, feature similarity, rankings or
  candidate suitability.
