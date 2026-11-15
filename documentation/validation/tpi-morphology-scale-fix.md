# TPI morphology scale failure repair

## Finding and correction

Discovery previously raised `ValueError: Planetary reference has no valid TPI
morphology normalization scale` when the reference support contained no valid
TPI samples or had zero TPI variance. This stopped otherwise valid processing
and prevented the evidence gate from reporting the actual limitation.

Terrain analytics now sets the morphology normalization scale to `null` when
no positive shared scale can be estimated. It writes an all-NoData morphology
raster and an explicit warning, without classifying unsupported observations
as neutral terrain. Discovery propagates this unavailable state to the Earth
analysis, permits the method only when both surfaces have zero morphology
samples, and leaves the morphology comparison distance unavailable. Since the
mission profile requires that feature, candidates remain unranked with
`insufficient_evidence`. Other feature processing and job completion continue.

## Verification

Automated checks run:

```text
ruff check [modified backend modules and tests]     passed
pytest tests/scientific/test_terrain_analytics.py \
       tests/scientific/test_analogue_discovery.py  40 passed
```

The backend container was rebuilt and restarted. Health returned `healthy`,
with PostgreSQL connected and PostGIS 3.4 available.

A live discovery job used the actual MGS MOLA product `MEGT44N000HB` and the
actual USGS 1 m bare-earth Idaho DEM manifest. The request used a 10 km Earth
support and 10 km Mars reference support, with 2 km candidate windows and a
requested 30 m target. The job completed successfully:

| Result | Value |
| --- | --- |
| Job | `81bc359c-7e52-445e-9f0d-1c2f459b03a3` |
| Discovery run | `0bff2433f83bc38e971e` |
| Windows generated / evaluated | 36 / 36 |
| Eligible / ranked candidates | 0 / 0 |
| Mars landform scale / samples | unavailable / 0 |
| Earth landform scale / samples | unavailable / 0 |
| Candidate status | all `insufficient_evidence`; no rankings |

The published Mars and Earth terrain-analytics reports both record a null
normalization scale, zero valid morphology samples, and the explicit warning
that no class threshold was invented. The discovery report records that the
Mars reference coverage is below the evidence threshold. The successful job
is therefore evidence that the exception is repaired, not evidence that a
candidate analogue has been found.

## Changed behavior and scope

The standalone `classify_relative_landform` helper can still classify a
provided positive-scale TPI raster. The production analytics pipeline no
longer assigns neutral class zero when a scale is absent or zero. An
intentionally disabled Earth morphology analysis is recorded as unavailable,
not independently normalized. No terrain measurements or candidate scores
were fabricated.
