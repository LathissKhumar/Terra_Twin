# Decision 0007: Persisted single-worker discovery orchestration

Status: Implemented for Phase 8

## Context

ScaleBridge, Terrain Analytics and analogue discovery can take longer than a
normal HTTP request. The UI must recover job state after reload, failures must
be auditable, and a partially generated candidate report must not be served.

## Decision

Persist request fingerprint, configuration payload, stage, progress, result ID,
failure, and lifecycle timestamps in PostgreSQL. Execute processing on one
bounded background thread in the API process. On startup, mark stale running
records interrupted and resume queued records. Stage all output in a per-job
directory and publish completed engine run directories atomically; publish the
discovery report last. Reuse identical active/successful configurations and
return explicit capacity errors.

## Consequences

This avoids a new broker and keeps job status durable across browser and
backend restarts. The worker is single-instance and single-threaded; multiple
API replicas need a database lease/claim protocol. A process can stop during
filesystem publication after some ancillary directories move, but no discovery
report becomes visible and the job remains failed/interrupted. Artifacts are
content/provenance referenced, not uploaded by arbitrary API path.
