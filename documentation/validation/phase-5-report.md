# Phase 5 — Earth analogue discovery report

## Scope and implementation

Implemented a deterministic discovery engine that consumes validated ScaleBridge
and Terrain Analytics artifacts. It validates source checksums, dataset IDs,
feature raster provenance, grids, CRS, feature algorithms/units/neighborhood
support, and metric postings before searching. It generates physical candidate
windows within a requested Earth boundary, crops an equal-sized support from
the planetary region, compares feature distributions, gates incomplete
observations, clusters overlapping windows, and writes full candidate and run
provenance to JSON.

No frontend mock data, hardcoded analogue site, machine-learning model, or
model training is involved. A separate synthetic end-to-end test verifies the
ranking path; the synthetic fixtures are test-only and are not reported as
scientific results.

## Real search configuration and inputs

- Planetary: MGS MOLA MEGDR median topography, `MEGC44N000HB`, dataset ID
  `14022166079edafc99650f354e5a634e6eb2c2ea544b444c01cd8ee55437df36`.
- Earth: Copernicus DEM GLO-30 Public DSM, dataset ID
  `51587b0a9af347ff0bfe95b51ccd4d145ffdf0f74fdf18ce0213028f8041d989`.
- ScaleBridge run: `4b76a5af44a9658065a4`.
- Terrain Analytics runs: Mars `4aa2a0f6cc4cd73fa047`; Earth
  `5cbea74eb4a9a04afd3b`.
- Planetary relative DEM SHA-256:
  `6b934428ef8d168c3260b32aaa538f2af9cb4c57ae40e74d8864d899d551cf3c`.
- Earth relative DEM SHA-256:
  `d6f7c3438e50cc902c0ad0ae1238683dcb38eb3296e238c23c20713f3b33034e`.
- Earth search boundary, WGS84 west/south/east/north:
  `77.2629323271279, 18.27396810860149, 77.73706767287212, 18.72587919382713`.
- Requested candidate width/height: 20,000 m; requested stride: 10,000 m.
- Actual Earth and Mars comparison windows: 44 × 44 cells at 463.000 m
  posting, 20,372.000 m × 20,372.000 m. Actual stride: 10,186.000 m.
- Planetary center crop: row 32, column 32, 44 × 44 cells; native Mars
  geographic bounds `77.31870582, 18.22806101, 77.68129418, 18.57185360`.
- Profile: `ROVER_MOBILITY_AND_TERRAIN_NAVIGATION` v1.0.0. All seven features
  required; minimum evidence coverage 0.80; minimum samples 20; maximum
  candidate count 10,000; overlap IoU threshold 0.1; bootstrap replicates 100.

## Actual result

The engine generated and evaluated 16 windows, grouped them into four overlap
clusters, and reported **0 eligible candidates and 0 ranked candidates**. This
is an evidence-gated real result. The equal-sized MOLA center crop contains 4
valid cells for slope and both curvature features (0.207% coverage) and 9
valid cells for local relief, roughness, TPI, and relative-position classes
(0.465% coverage), out of 1,936 cells. All features fail the 20-sample and
80%-coverage gates. The first Earth window has 1,849 valid cells per feature
(95.51% coverage). Per-feature distances and bootstrap errors are retained as
diagnostics, but no weighted distance or rank is produced.

Effective spatial resolution for both products is unavailable. The 463 m
posting is not treated as effective resolution. Terrain Analytics feature
maps inherit the 1,389 m neighborhood, which can extend outside each candidate
boundary. Results do not establish rover-scale mobility or material
transferability.

Example retained candidate: `63af46cd196d205c2d9071d9`, centroid
77.3595909715°E, 18.6338028281°N, status `insufficient_evidence`, combined
coverage 0.002066, weighted distance and rank null. The report contains all 16
windows, geographic polygons and centroids, pixel offsets, per-feature
measurements and differences, source-specific coverage, warnings, data IDs,
checksums, profile, configuration, and software versions.

The reproducible result is
[`report.json`](../../data/results/analogue_discovery/adc68c9d64de024497c0/report.json):
run ID `adc68c9d64de024497c0`, engine version `0.5.1`, digest
`adc68c9d64de024497c0454d38d9867b9e5d243187725bee430de83dbb8600a2`. The
actual CLI was run twice; both runs returned identical IDs, digest, and counts.

## Review findings addressed

- Corrected an unfair scale comparison: the previous run compared a 20 km
  Earth window against the entire ~50 km planetary feature raster. Engine
  0.5.1 now extracts an equal-size central planetary support and records its
  dimensions and native geographic boundary.
- Added explicit rejection when planetary/Earth pixel postings differ beyond
  tolerance or the chosen window cannot fit the planetary reference.
- Added compatibility validation for feature methods, units, neighborhoods,
  and aggregation, plus projected-metre CRS checks on both source grids.
- Added separate planetary and Earth feature coverage reporting and applies
  both to evidence gates.
- Added per-candidate configuration/profile/upstream-run provenance.
- Added end-to-end synthetic ranking/reproducibility coverage and a selected
  features/profile mismatch error-path test.

## Commands and validation

Executed:

```text
uv run --directory backend python scripts/run_analogue_discovery_real.py
uv run --directory backend python scripts/run_analogue_discovery_real.py
uv run --directory backend pytest -q
76 passed, 1 skipped
uv run --directory backend ruff check app scripts/run_analogue_discovery_real.py tests/scientific/test_analogue_discovery.py
All checks passed
uv run --directory backend mypy app scripts/run_analogue_discovery_real.py
Success: no issues found in 49 source files
git diff --check
```

The skipped test is an existing environment-dependent test. Both real runs
produced the same reproducibility digest. No raw source elevation files were
modified by discovery.

## Acceptance and limits

**Phase 5 implementation and its real-data execution are complete.** All
requested engine behaviors are implemented and tested. The real-data acceptance
run is reproducible, but it yields no ranked candidate because the selected
MOLA support fails the explicit evidence gate. That is an accepted scientific
outcome under the Phase 5 instructions, not a claim that the MOLA-to-Earth
feature match has been established. A better-supported planetary reference
region or denser documented DTM is required to obtain eligible real candidates.

No Phase 6 work has started.

## Independent audit addendum — later HiRISE discovery result

The MOLA run above remains a valid historical insufficient-evidence result.
After registering the documented HiRISE Jezero DTM and correcting unequal
ScaleBridge supports, the application produced a later real bounded run:
`a2070ff303aaf4cf075e` (engine `0.6.0`, reproducibility digest
`a2070ff303aaf4cf075e4c4e6f21adfb8eb3e747641d6efa5b26814747a679b8`). It
searched the WGS84 boundary
`[77.45253008461685, 18.454716171043245, 77.54746991538315,
18.545277668852417]`, about 10 km × 10 km, and evaluated 25 windows. All 25
passed the run's configured evidence gates and were ranked. Rank 1 is
`2c36fc1941cc6e7bf528b0e5`, centroid 77.5189247422°E, 18.4999990538°N,
weighted distance 0.1190669273, coverage 0.9403122. The score was independently
recomputed from stored feature distances and versioned weights. This is a
bounded provisional terrain-morphology ranking, not a global novelty or
rover-suitability claim. Full actual source, configuration and per-feature
values are in [`independent-phase-audit.md`](independent-phase-audit.md).
