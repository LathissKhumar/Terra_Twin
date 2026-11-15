# Analogue discovery methodology

## Purpose and inputs

The discovery engine slides physical-size windows across a user-defined Earth
study boundary, compares their terrain-feature distributions with a like-sized
central window from a selected planetary feature region, records evidence, and
only ranks candidates that pass all configured evidence gates. A lower distance
means closer under the specified features, normalization, and mission profile.
It is not universal suitability, probability, or a similarity percentage.
Absence from a bounded search is not evidence of global novelty.

Inputs are checksummed ScaleBridge relative-elevation rasters, matching Terrain
Analytics outputs, and their machine-readable reports. Dataset IDs, DEM hashes,
feature raster hashes, CRS, dimensions, transforms, algorithms, units,
neighborhood support, and aggregation are cross-checked. Planetary and Earth
postings must agree within 0.1%. Both comparison grids must use a projected
CRS with metre horizontal units; geographic degrees and non-metric projected
units are rejected. Mars and Earth remain on independent local grids; only feature
distributions are compared. Absolute elevation and cross-body coordinates are
never compared.

## Candidate generation and geographic bounds

Window width, height, and stride are specified in metres. Dimensions use
ceiling division to grid cells; stride uses nearest-integer rounding (at least
one cell). Actual dimensions and strides are recorded. Windows must fit inside
the raster and have their full densified geographic perimeter inside the
requested WGS84 rectangle. The last valid offsets are appended to cover raster
edges; duplicate row/column positions are not emitted. The default study
boundary is the Earth raster envelope. A maximum-candidate overflow fails
explicitly instead of silently truncating the search.

Candidate IDs hash the processing configuration and exact pixel window. Each
result records the WGS84 polygon and centroid, pixel position, measurements,
coverage, warnings, source dataset IDs/checksums, and upstream run IDs.
Overlapping windows are grouped by intersection-over-union (IoU); only the
lowest-distance eligible representative can be ranked. Equal distances use
candidate ID as the deterministic tie-breaker. Nonrepresentatives and
insufficient-evidence windows remain in the report.

## Planetary and Earth support matching

The engine extracts a centered planetary crop with the same number of cells as
an Earth candidate window. Both supports therefore have the same reported
physical dimensions when their ScaleBridge postings match. The crop location,
dimensions, and native planetary-body geographic bounds are recorded. This
prevents comparing a small Earth candidate distribution against an entire,
larger planetary region. It does not imply that the planetary raster has the
same effective resolution or data quality as the Earth raster.

## Feature distances and weights

The initial `ROVER_MOBILITY_AND_TERRAIN_NAVIGATION` profile v1.0.0 requires all
seven configured features: slope (0.20), local relief (0.18),
elevation-dispersion roughness (0.18), profile curvature (0.12), plan curvature
(0.12), TPI (0.12), and relative-position morphology (0.08). These weights
are provisional researcher choices with written rationales, not validated
mission-science values. Researchers can load a modified, versioned profile.
The selected feature set must match the profile's weighted required features.

For continuous features, raw distribution distance is the first Wasserstein
distance `W1` in the feature's documented units. The normalized distance is:

```text
d_i = W1(reference, candidate) / max(IQR(reference), configured_scale_floor_i)
```

The scale uses only the planetary reference IQR and a unitful configured
floor. Defaults are 1 degree (slope), 1 m (local relief), 0.5 m (roughness),
1e-5 m⁻¹ (each curvature), and 1 m (TPI). Results include both distributions'
summary statistics, signed median difference, raw `W1`, normalized distance,
and bootstrap standard error. Relative-position classes use total variation
distance `0.5 * sum(abs(p_reference - p_candidate))` over low/near-mean/high
fractions; this categorical distance is in [0, 1].

The weighted distance is emitted only if all required features have the
configured minimum count and coverage in both sources:

```text
D = sum(weight_i * d_i) / sum(weight_i)
```

Defaults require at least 20 valid samples and 80% coverage per feature per
source. Partial evidence never receives a weighted distance or rank. Per-feature
diagnostics may still be recorded, clearly separated from ranking. Bootstrap
standard errors estimate finite-sample distribution variability only; they do
not estimate DEM measurement, interpolation, effective-resolution, or
instrument uncertainty. The weighted uncertainty combines feature errors
assuming independence.

## Actual bounded search — engine 0.5.1

Command:

```sh
uv run --directory backend python scripts/run_analogue_discovery_real.py
```

Inputs are ScaleBridge run `4b76a5af44a9658065a4`, MOLA analytics run
`4aa2a0f6cc4cd73fa047`, and Copernicus analytics run `5cbea74eb4a9a04afd3b`.
Sources are MGS MOLA MEGDR median topography product `MEGC44N000HB` and
Copernicus DEM GLO-30 Public DSM. The bounded Earth search area (WGS84 west,
south, east, north) is:

```text
77.2629323271, 18.2739681086, 77.7370676729, 18.7258791938
```

The search evaluated the full approximately 50 km × 50 km Earth input raster,
not a manually selected analogue site. Requested windows are 20,000 m square
with 10,000 m stride. Both Mars reference and Earth candidate windows are
44 × 44 cells at 463.000 m posting (20,372.000 m square). Actual stride is
10,186.000 m. The planetary crop starts at row/column 32; its native Mars
body-geographic bounds are 77.31870582, 18.22806101, 77.68129418,
18.57185360 (west, south, east, north). All seven features are required,
minimum coverage is 0.80, minimum samples is 20, maximum candidate count is
10,000, and overlap IoU threshold is 0.1.

| Search outcome | Value |
| --- | ---: |
| Generated / evaluated Earth windows | 16 / 16 |
| Overlap groups | 4 |
| Eligible candidates | 0 |
| Ranked candidates | 0 |
| Reproducibility digest | `adc68c9d64de024497c0454d38d9867b9e5d243187725bee430de83dbb8600a2` |

The zero result is caused by reference evidence coverage, not by an absent
scoring path: the planetary crop has 4 valid cells (0.207%) for slope and both
curvatures, and 9 valid cells (0.465%) for the other features, out of 1,936
cells. Every feature falls below both configured evidence gates. The first
Earth candidate has 1,849 valid cells per feature (95.51%). No weighted score
is emitted. Effective spatial resolution is unavailable for both products;
463 m posting must not be interpreted as effective resolution.

Candidate `63af46cd196d205c2d9071d9`, centered at 77.3595909715°E,
18.6338028281°N, is retained as insufficient evidence. The following
feature-level statistics are diagnostics only, not accepted matches or ranks:

| Feature | MOLA samples / coverage | Earth samples / coverage | Raw W1 | Normalized distance | Bootstrap SE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Slope | 4 / 0.207% | 1,849 / 95.51% | 0.5187° | 0.5187 | 0.0679 |
| Local relief | 9 / 0.465% | 1,849 / 95.51% | 4.1550 m | 0.2895 | 0.1637 |
| Roughness | 9 / 0.465% | 1,849 / 95.51% | 1.9155 m | 0.5592 | 0.2421 |
| Profile curvature | 4 / 0.207% | 1,849 / 95.51% | 5.2225e−5 m⁻¹ | 2.1679 | 0.2369 |
| Plan curvature | 4 / 0.207% | 1,849 / 95.51% | 2.5047e−3 m⁻¹ | 5.6433 | 0.2549 |
| TPI | 9 / 0.465% | 1,849 / 95.51% | 2.1304 m | 0.5756 | 0.2299 |
| Relative-position classes | 9 / 0.465% | 1,849 / 95.51% | — (TV) | 0.4018 | 0.0114 |

Terrain features inherit the 1,389 m full-width neighborhood defined by Terrain
Analytics; that support can extend beyond an individual candidate polygon.
Results do not establish rover-scale mobility, material properties, global
novelty, or transferability.

The full report is
`data/results/analogue_discovery/adc68c9d64de024497c0/report.json`. Running the
real command twice yielded the same run ID and digest. An end-to-end synthetic
test separately verifies stable distance-ordered ranking when evidence is
adequate; its fixtures are test data and are not presented as scientific
results.

No machine-learning model or training is used. This is a deterministic
statistical comparison engine; bootstrap resampling estimates sampling
variation and is not model training.
