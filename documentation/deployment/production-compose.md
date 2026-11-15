# Single-host production deployment

This deployment is a single-tenant, single-host Compose setup. Caddy provides
automatic HTTPS and one shared Basic Authentication account in front of both
the frontend and every API endpoint. PostgreSQL/PostGIS, FastAPI and Next.js
have no published host ports. This is appropriate for a protected research
instance; a public multi-user service needs identity management, per-user
authorization, rate limiting, and a separately sized job/storage architecture.

## Host requirements

- A Linux Docker host with Docker Compose v2.
- A DNS `A` record for the chosen hostname, and an `AAAA` record only if IPv6
  ingress is configured.
- Inbound TCP 80 and 443, plus UDP 443 if HTTP/3 is desired.
- Persistent storage for PostGIS, Caddy state, and TerraTwin data. Back up all
  three independently.
- Enough RAM and disk for the maximum raster/job sizes selected by the operator.
  The local validation results are not a general capacity benchmark.

## Configure and start

1. Copy `.env.production.example` to `.env.production`; use a unique random
   database password and select a real hostname whose DNS points to this host.
2. Generate a Caddy bcrypt password hash. Do not put the plaintext password in
   the Caddyfile:

   ```sh
   docker run --rm caddy:2.11.9-alpine caddy hash-password --plaintext
   ```

   Put the returned hash and login name in `.env.production`. Protect that file:

   ```sh
   chmod 600 .env.production
   ```

3. Set `TERRATWIN_PUBLIC_ORIGIN` to the exact `https://` origin. Set
   `TERRATWIN_DATA_DIR` to a persistent directory. The API container runs as
   UID/GID 10001; create the data folders and grant that identity write access.
4. Start and inspect the services:

   ```sh
   docker compose -f compose.production.yaml --env-file .env.production config
   docker compose -f compose.production.yaml --env-file .env.production up -d --build
   docker compose -f compose.production.yaml --env-file .env.production ps
   docker compose -f compose.production.yaml --env-file .env.production logs --tail=200
   ```

5. Browse to the configured HTTPS hostname and authenticate. Caddy obtains and
   renews the certificate when public DNS and ports are reachable.

Do not publish ports 3000, 8000, or 5432 directly. The production Compose file
does not publish them. `compose.yaml` is a development stack and retains its
local development defaults; do not expose it to the public internet.

## Data and database backups

Raw source datasets are immutable and checksum-addressed; processed products
and manifests live under `TERRATWIN_DATA_DIR`. Stop writes or take a consistent
filesystem snapshot when backing up this directory. Back up PostGIS separately
with `pg_dump` from the database container, and retain the Caddy data volume so
TLS account/certificate state survives replacement. Test restore procedures
before relying on the deployment.

Migrations run as a one-shot service before the API starts. Inspect its logs
before diagnosing a backend health failure. Do not run `docker compose down -v`
on a production deployment: that removes the database volume.

## Deployment scope and known limits

- The shared Basic Authentication account protects the single-host interface;
  it is not per-user authentication or an authorization system.
- Discovery is persisted in PostgreSQL but runs in one in-process worker.
  Restart recovery marks interrupted work; it does not resume a partial raster
  computation.
- Independent validation remains `UNVALIDATED` until a separately sourced,
  spatially suitable, vertically reconciled reference DEM is ingested.
- External deployment has not been run from this repository because no host,
  DNS hostname, or operator-owned credentials were provided.
