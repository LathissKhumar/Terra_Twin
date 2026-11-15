# Terrain analytics methodology

## Scope and interpretation

This module computes deterministic morphometric descriptors from one validated
ScaleBridge output raster at a time. It does not train or invoke a machine
learning model. It does not rank analogue sites, infer geology, or restore detail
lost during resampling. A Mars raster and an Earth raster are analyzed in their
own local metric grids; matching array positions are not asserted to be the same
geographic places.

Inputs must be projected rasters with known linear horizontal units, known
convertible vertical units, an affine grid without rotation/shear, and the
ScaleBridge provenance tags. Elevations and grid distances are converted to
metres. Unknown units or missing provenance are errors; CRS is never guessed.
The current real-data source products do not declare effective spatial
resolution in the harmonized tags. This is recorded as unavailable. Nominal
posting must not be interpreted as effective resolving power.

## Algorithms and contracts

| Output | Method | Units | Support and edge/NoData policy |
| --- | --- | --- | --- |
| Slope | Horn weighted 3×3 finite differences; `atan(sqrt((dz/dx)^2+(dz/dy)^2))` | degrees | Both metric pixel spacings are used. Outer row/column and every stencil touching NoData are missing. |
| Local relief | Focal maximum minus focal minimum | m | Centered rectangular neighborhood; requires a valid center and at least 80% of the full window by default. Out-of-raster cells count missing. |
| Terrain roughness | Population standard deviation (`ddof=0`) of valid neighborhood elevations | m | Same configurable neighborhood and validity rule as local relief. This is elevation dispersion, not vector ruggedness or TRI. |
| Profile curvature | Directional second-derivative surface curvature along the steepest-slope direction | m⁻¹ | Centered 3×3 differences; convex is negative. Edges/NoData stencil missing; a non-flat zero-gradient critical point is undefined and missing. |
| Plan curvature | Directional second-derivative curvature perpendicular to steepest slope | m⁻¹ | Same stencil; convex is positive. Edges/NoData stencil missing; undefined non-flat zero-gradient point missing. |
| TPI | Center elevation minus arithmetic neighborhood mean, including center | m | Same configurable neighborhood and validity rule. Positive is locally high; negative locally low. |
| Relative-position class | TPI divided by raster-wide valid TPI population SD; `<−1` low, `>+1` high, otherwise near mean | category codes −1/0/+1 | Inherits TPI missing mask. If SD is zero all valid cells are 0. Descriptive single-scale classes only, not a formal landform or geological classification. |

The default focal radius is 463 m. The code converts this radius to separate
integer row/column radii using each cell spacing and rounds each radius upward.
With 463 m square posting this gives a 3×3 window, or 1,389 m full width in
each direction. The support is rectangular, not a circular buffer. Configuration
is recorded per run. An 80% threshold on a 3×3 neighborhood requires 8 valid
cells (ceiling of 7.2) as well as a valid center. Increasing the radius changes
the physical terrain process summarized and should be selected before scientific
comparison, not tuned to improve a result.

All maps are georeferenced GeoTIFFs. Float maps encode missing cells with the
output NoData sentinel; morphology uses int16 and −32768. Maps carry algorithm,
units, support, mask, source checksum, source dataset ID and reproducibility
digest tags. JSON reports include valid sample counts, valid coverage, mean,
median, population standard deviation, min/max, 5th/25th/75th/95th percentiles,
histograms or category counts, map checksums, parameters, software versions and
warnings. Very small summaries (<20 cells) are explicitly warned as descriptive
only. Fewer than 50% valid input cells also triggers a coverage warning.

## Numerical validity and reference methods

Slope uses the classic weighted 3×3 finite-difference construction documented
in [ArcGIS How Slope Works](https://pro.arcgis.com/en/pro-app/3.3/tool-reference/spatial-analyst/how-slope-works.htm).
Focal range and population dispersion use explicit neighborhood masks and
valid-cell counts, consistent with the distinction between focal statistics
and NoData handling described in
[ArcGIS How Focal Statistics Works](https://pro.arcgis.com/en/pro-app/3.6/tool-reference/spatial-analyst/how-focal-statistics-works.htm).
Curvature uses centered first and second differences and explicitly documented
directional formulas. Its signs follow the documented profile-negative/plan-
positive convexity convention in the
[ArcGIS Curvature tool reference](https://pro.arcgis.com/en/pro-app/3.4/tool-reference/spatial-analyst/curvature.htm);
this engine uses its own direct finite-difference equations and does not claim
numerical parity with that GIS tool.
TPI is a local elevation contrast, not absolute elevation; see the
[USGS regional TPI example](https://pubs.usgs.gov/sir/2012/5155/pdf/sir2012-5155_508.pdf).
Landform naming/classification has no single universally adopted scheme; the
output is therefore limited to relative-position classes, consistent with the
caution in the [USGS landform classification review](https://pubs.usgs.gov/of/2010/1335/pdf/usgs_of2010-1335.pdf).

Landform morphology uses a shared, positive reference-TPI population standard
deviation for cross-region comparison. If the reference TPI has no valid
samples or its population standard deviation is zero, no comparable class
threshold exists: the morphology raster is written entirely as NoData, its
normalization scale is `null`, and a warning records the reason. The Earth
analysis inherits that unavailable state instead of estimating an unrelated
Earth-only scale. Discovery can complete, but the absent required morphology
feature contributes to `INSUFFICIENT_EVIDENCE`; it cannot be interpreted as a
matching class distribution.

Tests compare against independently calculated analytic or direct array
references: exact slope for a plane, expected second derivatives for a
quadratic, and manually computed focal range/standard deviation/TPI on a small
array. Gaussian ridge/hill and bowl fixtures verify relative TPI polarity.
These are numerical checks of the implementation and do not claim bit-for-bit
parity with a proprietary GIS implementation.

## Real-data run and limits

Reproducible command from the repository root:

```sh
uv run --directory backend python scripts/run_terrain_analytics_real.py \
  --scale-bridge-run-id 4b76a5af44a9658065a4 \
  --output-dir data/derived/terrain_analytics_50km \
  --neighborhood-radius-m 463
```

The parent ScaleBridge run uses the real MGS MOLA MEGC44N000HB median
topography product and Copernicus DEM GLO-30 Public DSM. It requested a
50,000 m × 50,000 m window per body, independently centered at the configured
Mars and Earth coordinates; the grids have separate local azimuthal-equidistant
CRSs. Its common posting is approximately 463 m. It is a test region, not a
discovery result or analogue candidate. Parent provenance is in
`data/processed/scale_bridge/4b76a5af44a9658065a4/report.json`.

| Body | Valid input cells | Input coverage | Slope / curvature samples | Focal samples | Interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| Mars MOLA | 1,086 / 11,664 | 9.31% | 12 | 25 | Insufficient evidence for representative feature distributions. Derived pixels exist, but sparse observation support and the small sample counts preclude a representative profile. |
| Earth Copernicus | 11,664 / 11,664 | 100% | 11,236 | 11,236 | Feature summaries describe this processed test window only; not a candidate ranking or broad site characterization. |

The summary count for landform equals the focal count. The Mars run warns that
all feature summaries with fewer than 20 samples are descriptive only, that the
input support is sparse, and that effective resolution is undocumented. The
Mars raster remains usable to inspect map generation/masking but **does not pass
the scientific representativeness gate**. A denser independently documented
regional DTM, or a better-supported MOLA region, is required before meaningful
Mars-to-Earth feature-profile comparisons. MOLA posting does not support
rover-scale obstacle or boulder measurements here.

Generated run identifiers and reproducibility digests:

| Body | Run ID | Reproducibility SHA-256 |
| --- | --- | --- |
| Mars | `4aa2a0f6cc4cd73fa047` | `4aa2a0f6cc4cd73fa047c0fb127784626874db27cbc65a17dce8a54da55edcd8` |
| Earth | `5cbea74eb4a9a04afd3b` | `5cbea74eb4a9a04afd3b9ef0583323b0d2fc3be63207924de9366a19188822a7` |

Outputs reside under `data/derived/terrain_analytics_50km/{mars,earth}/<run-id>/`.
Raw input rasters are not modified. The feature outputs are derived products;
all source checksums and individual output checksums are in each `report.json`.

## Resolution and use limitations

ScaleBridge aggregated Copernicus's nominal ~30 m posting and MOLA's ~439 m ×
463 m nominal ground posting onto ~463 m cells; it did not create finer terrain
information. Effective resolution is unavailable for both inputs in the run
metadata. Derivatives are sensitive to aggregation, interpolation, source
measurement method, and chosen neighborhood. Relative elevation centering does
not reconcile Mars areoid and Earth orthometric vertical references; terrain
derivatives are local shape descriptors only. They do not establish rover
mobility, traction, soil mechanics, material composition or mission suitability.

The implementation is deterministic and has no learned weights or training
step. SciPy is used for neighborhood filtering; its selected version is pinned
in `backend/pyproject.toml` and `backend/uv.lock`.
