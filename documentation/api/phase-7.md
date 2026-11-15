# Phase 7 API: Assessment and Evidence Passport

All responses are sourced from persisted discovery/processing artifacts. The
API does not accept caller-supplied scientific measurements.

## Candidate assessment

`GET /api/v1/candidates/{candidate_id}/assessment`

Optional query: `mission_profile_id` (defaults to
`ROVER_MOBILITY_AND_TERRAIN_NAVIGATION`). Returns a versioned deterministic
assessment with category, evidence state, measurement references, missing
information and limitations for each finding. An unknown profile returns a
structured client error. Missing or inconsistent processing artifacts return a
service-unavailable error rather than a fabricated assessment.

## Evidence Passport

`GET /api/v1/candidates/{candidate_id}/evidence-passport`

Returns schema version `1.0.0`, dataset and processing provenance, feature
comparisons, coverage, uncertainty, Terrain Twin validation state, mission
assessment, missing evidence and limitations.

## Exports

- `GET /api/v1/candidates/{candidate_id}/evidence-passport/export?format=json`
- `GET /api/v1/candidates/{candidate_id}/evidence-passport/export?format=pdf`

Both export the same canonical passport. Responses use attachment disposition
and `Cache-Control: no-store`. Invalid `format` values are rejected by FastAPI
request validation. PDF rendering enforces a 5 MB output cap.

## Status semantics

- `SUPPORTED_WITH_LIMITS`: the configured per-feature evidence gate passes;
  only bounded terrain-test planning is in scope.
- `INSUFFICIENT_EVIDENCE`: one or more required feature observation gates fail.
- `ADDITIONAL_EVIDENCE_REQUIRED`: terrain-only input does not support a
  material/soil conclusion.
- `PROFILE_RULE_ONLY`: scope rule, not an Earth-site observation.
- `UNVALIDATED` / `UNAVAILABLE`: no valid independent elevation comparison is
  represented by the linked Terrain Twin record.
