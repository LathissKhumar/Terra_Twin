# ADR 0001: Modular Monolith Architecture

## Status
Architecture direction adopted; Phase 1 acceptance awaits user approval.

## Context
TerraTwin requires tight synchronization between geospatial array computation (NumPy, SciPy, Rasterio, GDAL), relational metadata storage (PostgreSQL/PostGIS), and responsive web presentation (FastAPI, Next.js). A microservices architecture at this stage would introduce significant RPC network latency for large raster transfers, deployment complexity, and synchronization overhead without clear scaling benefits.

## Decision
We adopt a **Modular Monolith** structure for the backend:
- Future scientific calculation logic belongs in `backend/app/engines/` as pure modules with zero framework or database dependencies. These packages are currently empty.
- Future application orchestration belongs in `backend/app/services/`; no scientific services are implemented yet.
- HTTP and serialization live in `backend/app/api/`.
- The database is shared across modules via clean repository abstractions.

## Consequences
- Engines can be unit tested and benchmarked directly using pytest and synthetic data fixtures without needing running HTTP servers or databases.
- Memory layout is efficient: arrays can be passed in-process between ScaleBridge, Analytics, and Mesh generation without network serialization.
- Future extraction of compute-heavy modules into dedicated worker nodes can be done cleanly along engine boundaries if profiling proves it necessary.

