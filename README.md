# TerraTwin
Planetary Analogue Discovery and Terrain Intelligence Platform.

Phase 2 provides verified MOLA and Copernicus GLO-30 dataset acquisition and
ingestion, provenance manifests, and compact source-derived test samples.
Analogue discovery, terrain analysis, terrain meshes and evidence passports are
not implemented.

## Requirements
Python 3.12, uv 0.13.6, Node.js 22.12+ (22 or 24 LTS recommended), npm and Docker
with Compose. Use the project's own environments. No other repository is needed.

## Container setup
From the repository root:
```sh
docker compose up --build -d --wait
docker compose ps
docker compose logs --tail=100
curl --fail http://localhost:8000/api/v1/health
```
Open http://localhost:3000. API documentation: http://localhost:8000/api/v1/docs.
Compose enables PostGIS through an Alembic migration before starting the API.
Services bind to loopback. The backend writes ingested datasets under `data/`;
Compose uses `TERRATWIN_UID`/`TERRATWIN_GID` (default 1000) for bind-mount access.
Set them to your host account IDs when they differ from 1000. Development database defaults are postgres/postgres,
database terratwin; these are not production credentials. Override through a
root .env based on .env.example. Changing credentials does not reinitialize an
existing database volume. Preserve that volume unless intentionally resetting data.
The frontend can start independently: docker compose up --build -d frontend.

## Native development
Start only the database with docker compose up -d db. In backend:
```sh
uv sync --locked
uv run --locked alembic upgrade head
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000
```
If you customize Compose credentials in root .env, set the same POSTGRES_USER,
POSTGRES_PASSWORD and POSTGRES_DB in backend/.env before running native migrations.
Keep POSTGRES_SERVER=localhost and POSTGRES_PORT=5433 for the native backend.
Root .env configures Compose; it is not automatically loaded by native settings.

Optional backend/.env uses backend/.env.example; settings load this file regardless
of working directory. Relative DATA_DIR is resolved against backend/. Use ../data
for repository data. Docker explicitly sets /app/data and mounts `data/` read-write
for dataset acquisition. Existing private .env files must not be committed.

In a separate terminal, in frontend:
```sh
npm ci --ignore-scripts
npm run dev
```
The frontend works when the API is unavailable and reports that state.
NEXT_PUBLIC_API_URL defaults to http://localhost:8000/api/v1. It is public and
embedded at build time; rebuild when changing it. No external fonts are fetched.

## Quality gates
In backend:
```sh
uv run --locked ruff check app tests migrations
uv run --locked ruff format --check app tests migrations
uv run --locked mypy app
uv run --locked pytest -q
RUN_DB_TESTS=1 uv run --locked pytest -q
```
The default suite skips the live database test. The second command set requires
the running PostGIS database and includes it. Tests disable dotenv loading and
normalize application settings. With custom database credentials, export matching
POSTGRES_* variables in the integration-test shell; these are retained only when
RUN_DB_TESTS=1. TERRATWIN_ENV_FILE can select an alternative settings file;
an empty value disables dotenv loading.

In frontend:
```sh
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
LIVE_STACK=1 npm run test:e2e
npm audit
```
CI repeats these gates and Compose startup. Browser installation may require
system dependencies; CI uses playwright install --with-deps chromium.
On an unsupported host OS, an installed Chromium can be selected explicitly:
`PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:e2e`.
Use LIVE_STACK=1 only after Compose is healthy; that mode runs both real-API and
offline browser checks against the existing stack.
Only test fixtures simulate service responses, never scientific results.

## Documentation
- [Architecture](documentation/architecture/system-overview.md)
- [Implementation plan](documentation/phase-1-plan.md)
- [Roadmap](documentation/development-roadmap.md)
- [API](documentation/api/phase-1.md)
- [Dataset API](documentation/api/phase-2.md)
- [Validation report](documentation/validation/phase-1-report.md)
- [Dataset ingestion specification](documentation/datasets/phase-2-ingestion.md)
- [Phase 2 report](documentation/validation/phase-2-report.md)

Each phase requires executed checks, independent review, documentation and explicit
approval before the next phase. Production authentication, processing limits,
job orchestration and scientific validation are future work.

