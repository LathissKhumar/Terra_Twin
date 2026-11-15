# Phase 4 — Terrain Analytics validation report

## Implemented

Implemented the deterministic terrain analytics engine in
`backend/app/engines/terrain_analytics/engine.py`, with strict Pydantic
configuration/report contracts in
`backend/app/domain/schemas/terrain_analytics.py`. The independently callable
interfaces are slope, local relief, roughness, profile curvature, plan
curvature, TPI and relative-position morphology classification. The raster
orchestrator produces a georeferenced GeoTIFF and metadata for each output,
plus a reproducibility report. See
[`terrain-analytics.md`](../scientific-methodology/terrain-analytics.md) for
formulas, units, support, signs, masks, source references and scientific limits.

No learned model or training is involved. SciPy 1.18.0 was pinned, resolved and
locked for the current Python 3.12 environment.

## Validation commands and results

Commands executed from the repository root:

```text
uv run --directory backend pytest -q
57 passed, 1 skipped

uv run --directory backend pytest -q tests/scientific/test_terrain_analytics.py
13 passed

uv run --directory backend ruff check app scripts/run_terrain_analytics_real.py tests/scientific/test_terrain_analytics.py
All checks passed

uv run --directory backend mypy app scripts/run_terrain_analytics_real.py
Success: no issues found in 47 source files

uv lock --directory backend --check
Resolved 49 packages in 2ms; lock is current

git diff --check
No whitespace errors
```

The tests use known analytic surfaces and direct reference calculations: a flat
plane, known-gradient planes, quadratic curvature, direct focal calculations,
Gaussian hill/ridge/valley TPI polarity, NoData holes, edges, multiple postings,
invalid CRS/units and an imperial linear horizontal CRS. They also verify
GeoTIFF output, units, mask coverage, and each independent callable. The one
skipped test belongs to the preexisting backend suite; no failure was observed.

Real-data execution:

```text
uv run --directory backend python scripts/run_terrain_analytics_real.py \
  --scale-bridge-run-id 4b76a5af44a9658065a4 \
  --output-dir data/derived/terrain_analytics_50km \
  --neighborhood-radius-m 463
```

The command completed successfully and wrote seven actual feature maps for
each source. The input files are the real MOLA MEGC44N000HB product and
Copernicus DEM GLO-30 Public DSM represented by ScaleBridge outputs. No
synthetic elevations were used for these real-data maps. Synthetic rasters are
used only in numerical tests. Inputs were read-only; feature maps were written
under `data/derived/terrain_analytics_50km/`.

## Real-data observations

Both output grids are 108×108 at about 463 m posting. MOLA valid support is
1,086/11,664 cells (9.31%); Copernicus valid support is 11,664/11,664 (100%).
For the 463 m radius (3×3 neighborhood, approximately 1,389 m full width),
Mars produced 12 slope cells and 12 cells for each curvature map, and 25 focal
cells for relief, roughness, TPI and relative-position classes. Earth produced
11,236 valid cells for each feature map. Effective spatial resolution is not
documented for either source in the parent run; nominal posting is not asserted
as effective resolution.

Examples of actual distribution summaries, shown only to demonstrate output
generation and not as representative Mars profile claims:

| Feature | Units | MOLA mean / median / SD | Copernicus mean / median / SD |
| --- | --- | ---: | ---: |
| Slope | degree | 3.1118 / 1.5643 / 3.3762 | 0.9229 / 0.8305 / 0.6417 |
| Local relief | m | 55.0526 / 27.9719 / 57.3617 | 22.2240 / 21.4388 / 13.5983 |
| Elevation-dispersion roughness | m | 18.2514 / 10.3734 / 19.0733 | 7.1194 / 6.8175 / 4.4412 |
| Profile curvature | m⁻¹ | −2.3194e−5 / 8.9158e−6 / 1.0488e−4 | 2.4251e−6 / 3.2112e−6 / 4.6800e−5 |
| Plan curvature | m⁻¹ | 9.3020e−4 / 2.0878e−4 / 2.0895e−3 | −5.3236e−5 / 3.0094e−5 / 5.0483e−3 |
| TPI | m | 4.0385 / 0.8703 / 10.1084 | −0.0104 / −0.2805 / 4.8708 |

Mars morphology classes: 0 relative-low, 21 near-local-mean, 4 relative-high.
Earth: 1,451 relative-low, 8,280 near-local-mean, 1,505 relative-high.
These labels are single-scale TPI categories, not geological/material classes.

### Acceptance status

**Implementation and automated numerical checks pass. Real maps were generated,
but the Phase 4 scientific acceptance gate is not fully met.** The selected
MOLA window is too sparsely supported for a representative Mars feature
profile: every Mars feature summary has only 12 or 25 observations, and total
input coverage is 9.31%. The engine warns that derivative maps with fewer than
20 samples are descriptive only and separately reports the 25-cell focal
sample count; the full coverage warning applies to all Mars outputs. It does
not fill missing values or claim meaningful Mars/Earth comparability. Mars
outputs are valid exploratory pipeline artifacts only. A denser documented
regional elevation source or a better-supported MOLA region is needed for
representative Mars statistics. Earth outputs describe one test window and are
not ranked analogues. Rover-scale obstacles, geological suitability and
mobility are not established by these data.

The final maps use Mars run `4aa2a0f6cc4cd73fa047` (reproducibility SHA-256
`4aa2a0f6cc4cd73fa047c0fb127784626874db27cbc65a17dce8a54da55edcd8`) and Earth
run `5cbea74eb4a9a04afd3b` (SHA-256
`5cbea74eb4a9a04afd3b9ef0583323b0d2fc3be63207924de9366a19188822a7`). These
final digests reflect the reviewed profile-negative / plan-positive convexity
signs. Parent ScaleBridge run ID: `4b76a5af44a9658065a4`; its report contains dataset,
input and artifact checksums and spatial assumptions. Terrain run IDs and
reproducibility hashes are recorded in the methodology page and each output
`report.json`. No Phase 5 work has started.

## Independent audit addendum — HiRISE-derived feature maps

The later integrated HiRISE run generated all seven feature rasters for the
selected Jezero reference and Earth support. Current analytics IDs are Mars
`1e842c2956e29eb78c7e` (66×66; 4,356 valid input cells; 4,096 valid full
3×3-stencil slope/curvature samples) and Earth
`53de3ba4f905c64e1852` (326×326; 106,276 valid input cells). Both use
30.7461555 m grid posting and a 30.746 m radius neighborhood (approximately
92.24 m full support). These maps support broad-scale morphology only. Source
effective resolution is undocumented, and this analysis does not identify
rover-scale obstacles or support operational mobility claims. Final live-run
details are in [`independent-phase-audit.md`](independent-phase-audit.md).
