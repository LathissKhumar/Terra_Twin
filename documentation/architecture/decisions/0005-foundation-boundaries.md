# ADR 0005: Phase 1 boundaries and reproducible development

Status: implemented; phase acceptance pending user review.

Only root metadata and health are mounted. Existing scientific route files are
reserved placeholders, not operational APIs. Engines, domain models and services
remain empty. No migrations create scientific tables or jobs yet.

Readiness returns 200 only if PostgreSQL and PostGIS are available; otherwise 503
with the same typed envelope. Root metadata is database-independent liveness.
Checks have a configurable timeout. Public errors never return exception text.

Python 3.12, exact direct dependency pins, uv.lock and npm package-lock.json define
the application installs. Docker uses uv sync --locked and npm ci. Scientific
dependencies from the preliminary scaffold are deferred until their phase so
native geospatial compatibility is tested deliberately. Node 22 container builds
and host Node 26 are validated separately. The lockfiles pin transitive packages.

Compose is local development only, bound to loopback with explicitly documented
development credentials. The existing named database volume is preserved.
The migration enables PostGIS; downgrade preserves that potentially shared
extension. No authentication or public deployment is claimed.

