# TerraTwin

TerraTwin is a planetary analogue discovery and terrain intelligence platform.
Its initial workflow compares a selected Jezero Crater MOLA reference support
with a user-selected Earth DEM support, computes terrain feature profiles,
searches Earth windows under explicit evidence gates, constructs a DEM-derived
Terrain Twin and produces a reproducible evidence assessment.

The app uses genuine dataset manifests and stored engine reports. The current
local Earth collection is one Copernicus DEM GLO-30 tile, so results are bounded
to its valid geographic coverage. A zero eligible-candidate result is a valid
scientific outcome when evidence gates are not met. Moon selection is available
when a validated lunar raster is present; no automatic LOLA downloader is
configured yet. A mesh is labeled `UNVALIDATED` without an independent elevation
reference.

## Requirements

Docker Engine with Compose, Node.js 22.12+ and npm for native frontend work,
Python 3.12 and uv 0.13.6 for native backend work.

## Run the full stack

From the repository root:

```sh
cp .env.example .env
docker compose up --build -d --wait
docker compose ps
docker compose logs --tail=100
```

Open <http://localhost:3000>. API documentation is at
<http://localhost:8000/api/v1/docs>; health is
<http://localhost:8000/api/v1/health>. Compose waits for PostGIS, applies
Alembic migrations, then starts the backend. Service ports are bound to
loopback. Change `TERRATWIN_UID` and `TERRATWIN_GID` in `.env` to your host user
IDs when needed for the data bind mount.

The compose `.env` values are local-development defaults, not production
credentials. Existing database volumes retain their initialized credentials
after environment changes. Do not delete a volume as a troubleshooting step if
it contains data.

## Workflow

1. Open Mission Explorer. Select the Mars/Moon reference region when available,
   inspect source manifests, and set the geographic center. The installed
   default Mars source is MOLA `MEGT44N000HB`.
2. Select a checksum-verified Earth source. Acquire a Copernicus GLO-30 tile at
   the selected center or stream a source GeoTIFF with its CRS and vertical
   metadata preserved.
3. Configure the metric comparison support, candidate window and stride, and
   evidence coverage threshold. Start processing.
4. The job continues in the backend and its state is stored in PostgreSQL.
   Refreshing the browser resumes status polling.
5. Inspect candidate boundaries, actual feature comparisons and evidence
   coverage. Unranked candidates remain visibly unranked.
6. Open Terrain Comparison, Terrain Twin or the candidate Evidence Passport.
   Export JSON or PDF from the Passport.

The configured Earth search boundary and candidate count are returned by the
actual discovery report. The workflow does not search or claim global Earth
coverage unless those data are explicitly ingested and included.

## Native development

Start PostgreSQL/PostGIS and apply migrations:

```sh
docker compose up -d db
cd backend
uv sync --locked
uv run --locked alembic upgrade head
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
cd frontend
npm ci --ignore-scripts
npm run dev
```

Set `NEXT_PUBLIC_API_URL` to the public API origin plus `/api/v1` before the
frontend build. It is public build-time configuration and must never contain
secrets. For native backend settings, use `backend/.env.example`; the native
database host/port defaults are `localhost:5433`. Root `.env` configures
Compose and is not loaded by native backend settings.

The Discovery map uses the OpenFreeMap Liberty basemap by default, with
candidate polygons coming only from TerraTwin discovery results. MapLibre
shows the source attribution. Set `NEXT_PUBLIC_MAP_STYLE_URL` at frontend
build time to use a different MapLibre-compatible style.

## Quality checks

Backend:

```sh
cd backend
uv run --locked ruff check app tests migrations
uv run --locked ruff format --check app tests migrations
uv run --locked mypy app
uv run --locked pytest -q
RUN_DB_TESTS=1 uv run --locked pytest -q
```

Frontend:

```sh
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
npm audit
```

Playwright browser checks are configured with `npm run test:e2e`; use
`LIVE_STACK=1` only after Compose health checks pass. Test fixtures may model
API responses but never scientific candidate or measurement results.

## Persistence and backup

Compose stores PostgreSQL in the `terratwin_pgdata` named volume and source,
processed, derived and result artifacts under `./data`. Keep them backed up as
a provenance-linked set: database records reference artifact IDs and processing
reports. A minimal maintenance-window backup from the host is:

```sh
docker compose exec -T db pg_dump -U postgres -d terratwin -Fc > terratwin-db.dump
tar --exclude='data/.staging' -czf terratwin-data.tar.gz data
```

Use matching configured database credentials if they differ from the local
default. Verify restore procedures in a separate environment before relying on
the backup. Protect raster archives as scientific source records.

## Deployment and limits

`compose.yaml` is the local development stack and must not be exposed directly.
A separate single-host production Compose setup with Caddy HTTPS and a shared
Basic Authentication gate is documented in
[production deployment](documentation/deployment/production-compose.md). It
does not provide per-user authentication or authorization. The job worker is
single-instance, one processing thread; horizontal worker scaling requires
database leasing. Production sizing still requires workload-specific profiling.

See [architecture](documentation/architecture/system-overview.md),
[scientific methods](documentation/scientific-methodology/README.md),
[datasets](documentation/datasets/phase-2-ingestion.md),
[API integration](documentation/api/phase-8.md), and the
[Phase 8 engineering report](documentation/validation/phase-8-report.md).
