# Phase 1 implementation plan

Scope: finish and validate the existing application foundation. No dataset acquisition,
scientific computation, candidate discovery, or geospatial dashboard.

## Inspection

Existing uncommitted scaffold includes FastAPI, database sessions, seven tests,
frontend dependencies and primitives, Compose, and architecture drafts. Preserve
these foundations while correcting unsafe path checks and incomplete wiring.
Python 3.12 is available in backend/.venv; host default is 3.14. Node is 26.
Docker requires host socket access. An existing TerraTwin PostGIS container and
volume must be preserved.

## Implementation sequence

1. Backend: revise app/core configuration/security/errors, database lifecycle,
   health schema/route and tests. Expose only implemented routes. Health reports
   readiness with 503 on unavailable dependencies and never exposes raw errors.
2. Frontend: add App Router shell, health status component, error/loading states,
   API contract validation, component/client tests, lint configuration, Dockerfile.
   Preserve existing theme and button foundation. No scientific numbers.
3. Dependencies/infrastructure: pin resolved versions and lockfiles, correct data
   mount, loopback bindings, database credentials via environment, migration
   startup, bounded health checks. Add Docker ignore files and CI.
4. Documentation: replace aspirational present-tense claims in architecture files;
   add root setup guide, roadmap, compatibility notes and validation report.
5. Execute installs, lint/format/type/test checks, frontend production build,
   native process smoke checks, database migration/PostGIS query and Compose
   startup/log inspection. Obtain independent review and address findings.

## Interfaces

GET /api/v1/health -> HealthResponse; readiness status healthy/degraded, database
connected/PostGIS flags. Error envelope has type/message/details/path. Settings
are environment-backed. Scientific engines and services remain reserved modules.
Frontend fetches only health; database access stays exclusively in backend.

## Risks and assumptions

Native scientific dependencies require a compatible NumPy/GDAL/PROJ build;
defer scientific dependencies until their phase rather than install unused tools.
No source dataset or scientific assumptions are accepted in this phase. Existing
illustrative thresholds, provenance values and rover limits are not validated.
Avoid memory-heavy simultaneous builds. Existing .env values are private and
must not be printed. Preserve the existing database volume.

## Acceptance gate

Independent frontend/backend startup, typed health response, PostgreSQL/PostGIS
verification, successful migration, lint/format/type/tests/build and Compose
startup, truthful documentation, no external project dependencies. Record exact
commands/results and limitations. Phase 2 requires explicit user approval.
