# Backend architecture

## Implemented responsibilities
- app/main.py: lifecycle, CORS, safe exception envelopes, root metadata and API mount.
- core/config.py: validated environment settings and database URL construction.
- core/logging.py: structured logging (JSON in production, readable locally).
- core/security.py: internal artifact path containment including symlink resolution.
- api/routes/health.py: HTTP readiness and validated response.
- domain/schemas/health.py: health contract.
- database/session.py: bounded PostgreSQL/PostGIS checks and async session factory.
- database/base.py: ORM base and timestamp mixin.
- migrations/: Alembic migration enabling PostGIS. Downgrade preserves the extension.

Only root and health routes are mounted. Other route files remain unmounted
scaffolding. Services, repositories, domain models and scientific engines are
reserved packages with no operational implementation.

## Interfaces
check_database_health() -> DatabaseHealth is async and dependency-injected into
the health route, allowing deterministic API tests. It has a total timeout and
sanitized failure codes. Database sessions roll back on failure and close after
use; the application disposes the engine on shutdown.

GET /api/v1/health returns HealthResponse with HTTP 200 when PostgreSQL and PostGIS
are available, otherwise HTTP 503. GET / is dependency-independent liveness.
HTTP and validation failures use error.type/message/details/path; validation
responses omit raw submitted values. Unexpected exceptions never expose text.

## Planned orchestration
Services will coordinate engines and persisted jobs. Engines take explicit
configuration and validated geospatial inputs, returning results plus provenance.
A PostgreSQL job table and bounded worker will handle durable execution and
restart recovery. An asyncio task alone is not a durable job mechanism.
No distributed broker or job execution is introduced in Phase 1.

The current path helper is defense in depth, not an atomic file-opening API.
Future ingestion must address races, upload limits, raster limits and authorization.

