# ADR 0002: Runtime and dependency management
Status: revised in Phase 1.
Use Python 3.12 with uv and an exact lockfile. The host's default interpreter is
not the project interpreter. Use backend/.venv or uv run --locked.
Use Next.js App Router and strict TypeScript. Exact frontend versions and npm ci
make installs reproducible. Docker validates a Node 22 environment separately.
Scientific native packages are deferred to their implementation phase. No claim
of GDAL/NumPy/PROJ binary compatibility is made by this foundation.
See ADR 0005 and dependency-compatibility.md.

