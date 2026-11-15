# Terrain-to-Test Intelligence and Evidence Passports

## Scope

Phase 7 implements a deterministic, evidence-linked assessment for
`ROVER_MOBILITY_AND_TERRAIN_NAVIGATION`. It consumes the stored analogue-discovery
report, its exact ScaleBridge report and dataset manifests, and an optional
Terrain Twin record. It does not perform terrain calculations or infer rover
safety, performance, or site suitability.

The authoritative profile is
[`rover_mobility_and_terrain_navigation_v1.json`](../../backend/config/mission_profiles/rover_mobility_and_terrain_navigation_v1.json).
It is version `1.0.0`, marked provisional. Its seven weights sum to one and are
researcher-set priorities. They are copied from the matching discovery profile;
the assessment engine does not change or re-compute the discovery weighted
distance.

## Evidence rules

For each required terrain feature, the engine marks a comparison
`SUPPORTED_WITH_LIMITS` only if the candidate is eligible, the feature is not
missing, both surfaces meet the discovery run's minimum sample count and
coverage, and a normalized distribution distance exists. This status means the
comparison passed those configured evidence gates. It does not mean a physical
Earth-to-Mars transfer has been experimentally validated. Otherwise the feature
is `INSUFFICIENT_EVIDENCE`; its measured summaries remain visible, while the
engine withholds a supported-similarity interpretation.

The candidate-level discovery eligibility, ranking and weighted distance are
copied from the immutable discovery report. An insufficient candidate retains
null rank and null weighted distance. Finite-sample standard errors are labeled
as distribution-distance variability and are not treated as DEM measurement
uncertainty.

The profile rules classify soil mechanics, subsurface composition, wheel
traction, dust behavior and material properties as requiring additional
observations. Gravity, vacuum, radiation and a complete planetary atmosphere
are profile-scope statements: they are not measurements of an Earth site.

Independent Terrain Twin validation is read from a twin matching the candidate,
discovery run and Earth dataset. If no such record or no suitable independent
reference exists, the passport records `unavailable` or `unvalidated`, with no
accuracy metrics. It never validates a mesh against its own source raster.

## Provenance and reproducibility

Passport schema `1.0.0` binds the candidate and discovery run to checksummed
source rasters, dataset manifests, the ScaleBridge report, the mission-profile
file and any matching Terrain Twin metadata/mesh. The reproducibility digest is
computed from the source artifact checksums and profile/configuration identity;
the generated timestamp is excluded so repeated generation from unchanged
inputs yields the same passport ID and digest.

JSON is the canonical full record. PDF renders that record and does not add
independent calculations. Both formats distinguish stored measurements from
deterministic interpretations, include missing evidence and limitations, and
carry source/reproducibility identifiers. The browser report displays the same
API fields and does not calculate scientific values.

## API

- `GET /api/v1/candidates/{candidate_id}/assessment`
- `GET /api/v1/candidates/{candidate_id}/evidence-passport`
- `GET /api/v1/candidates/{candidate_id}/evidence-passport/export?format=json`
- `GET /api/v1/candidates/{candidate_id}/evidence-passport/export?format=pdf`

Only the configured profile ID is accepted. Unknown profiles are rejected;
public requests cannot provide raster paths or raw processing inputs.

## Limitations

- Profile weights and rules are explicit provisional configuration, not
  validated rover engineering requirements.
- Elevation-derived geometry cannot establish soil, traction, dust, material,
  gravity, radiation, vacuum or atmospheric equivalence.
- An eligible discovery is a result under the chosen study boundary,
  resolution, feature normalization, coverage thresholds and profile; it does
  not establish universal analogue quality.
- Planetary measurement uncertainty is not available in all source products.
- PDF output is a readable summary of the canonical JSON, not a separate
  scientific record.
