# Phase 7 implementation plan — assessment and evidence passport

## Repository findings

- Assessment and evidence route files currently return placeholder messages and
  are not mounted by `api_v1.py`.
- The current DiscoveryReport contains its candidate-level feature summaries,
  distribution distances, valid counts, coverage, uncertainties, provenance,
  mission profile/configuration, and a missing weighted distance/rank when
  evidence gates fail.
- The selected current real candidate is
  `63af46cd196d205c2d9071d9` from run `adc68c9d64de024497c0`; all 16 current
  candidates are `insufficient_evidence`. Its limiting planetary feature
  coverage is 0.002066 (0.2066%), compared with the discovery gate of 0.80.
- The matching Phase 6 terrain twin is
  `7a7d7e5aa32745313b158d21`, with status `unvalidated`, no reference metrics,
  and actual mesh metadata/artifacts.
- Source manifests are stored under `data/manifests/`; ScaleBridge and
  discovery reports are in their run-scoped result directories. The latest
  discovery report embeds terrain feature comparisons; there are no standalone
  `data/results/terrain_analytics` reports.
- `reportlab` is not currently installed. The official ReportLab documentation
  describes `pdfgen`/Platypus PDF generation; the current official PyPI page
  lists ReportLab 5.1.0 and Python 3.12 support. Pin 5.1.0, verify resolution
  and runtime import before relying on it.

## Architecture and files

### Configuration and domain

- Add `backend/config/mission_profiles/rover_mobility_and_terrain_navigation_v1.json`:
  versioned profile, feature weights copied from the discovery run profile,
  required and optional evidence, category definitions, evidence gates,
  deterministic rules, and limitations.
- Add `backend/app/domain/schemas/mission_assessment.py` and
  `evidence_passport.py`: strict Pydantic records for evidence references,
  findings, coverage status, profile, validation, provenance, passport and
  reproducibility identifiers.

### Engines, services, and APIs

- Add `backend/app/engines/mission_evaluation/assessment.py`: pure deterministic
  assessment function. It will not calculate a new terrain score, promote an
  ineligible candidate, infer soil/environmental evidence, or claim rover
  safety/performance.
- Add `backend/app/services/assessment_service.py`: safe resolution and
  validation of candidate, discovery report, dataset manifests, ScaleBridge
  report, and matching terrain twin from configured data roots.
- Add `backend/app/services/evidence_service.py`: construct a versioned
  provenance-complete passport and reproducibility digest from those exact
  source records.
- Replace the placeholder handlers in
  `backend/app/api/routes/assessments.py` and `evidence.py` with candidate-scoped
  GET routes. Mount both in `backend/app/api/api_v1.py`.
- Add a bounded PDF renderer in `backend/app/services/evidence_pdf.py` using
  pinned ReportLab 5.1.0. JSON export is the canonical machine-readable record;
  PDF is a readable rendering of the same passport.

### Frontend and test coverage

- Add `frontend/types/evidence-passport.ts`,
  `frontend/lib/evidence-api.ts`, a readable report component, and
  `frontend/app/candidates/[candidateId]/passport/page.tsx`.
- Link the currently selected actual discovery candidate from the Terrain Twin
  view to its passport. Provide JSON/PDF export links and explicit measured vs
  interpreted labels.
- Add scientific tests for sufficient/insufficient evidence, missing
  validation, contradictory feature differences, no soil/environmental data,
  unsupported experiment, and deterministic passport IDs/content.
- Add API tests against the actual latest discovery report and compact local
  sources. Add frontend tests for the insufficient-evidence/UNVALIDATED report
  and export links.

### Documentation

- Add `documentation/scientific-methodology/terrain-to-test-assessment.md`,
  API contract notes, `documentation/decisions/0004-deterministic-assessment-and-passport.md`,
  and `documentation/validation/phase-7-report.md`.

## Assessment rules and assumptions

1. The candidate and discovery run are authoritative. Their status, rank,
   weighted distance, comparisons, coverages and uncertainty are copied as
   reported; they are not recomputed or overridden.
2. Coverage and minimum sample gates come from that run's stored configuration
   (currently coverage 0.80 and 20 samples). A feature comparison below either
   gate may be shown as an observed pipeline output but is not interpreted as
   supported similarity evidence.
3. `POTENTIALLY_TRANSFERABLE` applies to terrain geometry/slope/roughness and
   navigation geometry as a test-domain category. Its per-finding evidence
   status is still insufficient for this candidate.
4. Soil mechanics, subsurface composition, traction, dust and material
   properties are marked `REQUIRES_ADDITIONAL_EVIDENCE`; no relevant
   measurements are in the ingested inputs.
5. Gravity, vacuum, radiation and a complete planetary atmosphere are marked
   `CANNOT_BE_REPRODUCED_BY_THE_EARTH_SITE_ALONE` by profile rule; no numerical
   values or false experimental equivalence are attached.
6. Missing independent terrain validation stays `UNVALIDATED`; it does not
   become a zero error or a confidence percentage.
7. Any missing source file, checksum mismatch, malformed run, unknown profile,
   or unsupported experiment returns a structured error; no placeholder
   passport is generated.

## Risks

- Historical result directories can contain multiple runs and stale terrain
  twins. Matching must use candidate ID, discovery run ID, dataset ID and source
  provenance together, rather than simply selecting the newest twin.
- The Earth source is a DSM; reports must name the surface model and avoid
  implying bare-earth soil or traction measurements.
- The MOLA support is extremely sparse at the comparison window; the reader
  must see actual counts and the gate failure before any narrative conclusion.
- A PDF renderer may produce unsafe markup if raw manifest strings are fed to
  ReportLab Paragraph markup; escape all interpolated text and constrain PDF
  output size.
- Assessment rules are a versioned engineering policy, not validated rover
  engineering thresholds. The UI and passport must state this directly.

## Acceptance criteria

- The actual selected candidate receives an assessment and passport from its
  true stored processing records.
- Every feature measurement links to feature name, source run, dataset and
  comparison method; each unavailable input is explicitly marked.
- Discovery `insufficient_evidence`, null weighted distance/rank and Terrain
  Twin `UNVALIDATED` are preserved.
- Rule categories have transparent evidence and do not claim planetary
  equivalence, rover safety or performance.
- JSON parses against the versioned schema; PDF opens and contains the same
  key values/categories; the browser report displays them accurately.
- Scientific/API/frontend tests, lint, typecheck and production build pass.
- No Phase 8 work begins before explicit approval.

## Implementation status

The Phase 7 implementation and acceptance evidence are recorded in
[`phase-7-report.md`](../validation/phase-7-report.md). The canonical profile,
assessment service, versioned passport, JSON/PDF exports, browser report, and
live API/browser verification are complete. Phase 8 remains gated on explicit
approval.
