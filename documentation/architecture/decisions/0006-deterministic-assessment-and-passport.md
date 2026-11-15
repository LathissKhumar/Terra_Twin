# ADR 0006: Deterministic assessment and evidence passport

- Status: Accepted for Phase 7 implementation
- Date: 2026-11-15

## Context

Experiment transferability claims need traceable evidence and explicit unknowns.
An unconstrained language model or a generic suitability score would obscure
the line between DEM observations and physical conclusions.

## Decision

Implement a versioned deterministic profile and rule engine. Assessment records
reference immutable discovery feature outputs, source dataset IDs, configured
coverage/sample thresholds and matching Terrain Twin validation state. Store a
versioned Pydantic passport as the canonical report model; expose that model as
JSON and render PDF from the same model. The frontend renders backend outputs
only.

Profile weights remain provisional, visible and tied to discovery profile
version. Unknown materials and environmental properties remain explicit gaps.
Missing independent validation remains `UNVALIDATED`/`UNAVAILABLE` without
metrics.

## Consequences

- Findings are auditable and deterministic for identical source artifacts.
- Passport identifiers can be reproduced from source checksums and configuration.
- New experiment profiles require deliberate versioned configuration and
  matching discovery support.
- Readable prose and visual presentation cannot override the structured record.
- Human scientific review remains necessary before treating profile choices as
  validated experimental design guidance.
