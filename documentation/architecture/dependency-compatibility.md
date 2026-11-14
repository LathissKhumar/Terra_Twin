# Dependency compatibility
Reviewed against official documentation on 2026-11-14:
- https://nextjs.org/docs/app/getting-started/installation
- https://nextjs.org/docs/app/api-reference/config/eslint
- https://fastapi.tiangolo.com/deployment/versions/
- https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- https://ui.shadcn.com/docs/installation/manual
- https://rasterio.readthedocs.io/en/stable/installation.html

Next.js 16 uses ESLint directly rather than next lint. The client uses App Router,
React and Tailwind 3, retaining the existing theme; no Tailwind 4 APIs are assumed.
Pydantic Settings explicitly disables automatic JSON decoding for the CORS field,
then validates JSON-array or comma-separated input. SQLAlchemy URL construction
escapes credentials and selects psycopg/asyncpg drivers explicitly.

Direct versions are exact in manifests; transitive versions and integrity hashes
are in lockfiles. Install with uv sync --locked and npm ci. Base image tags pin
runtime releases, and PostGIS additionally pins the inspected image digest.

For Phase 2, Rasterio 1.5.2 and NumPy 2.5.4 are pinned together. Rasterio's
official metadata requires Python 3.12+, NumPy 2+, and GDAL 3.8+ for the 1.5
series; the installed wheel exposes GDAL 3.12.2. PyProj 3.7.2 is also pinned.
The executed environment successfully opens the PDS3 MOLA detached-label image
with GDAL's PDS driver and the Copernicus COG with the GTiff driver. Rasterio
1.5.2 avoids the NumPy 2.5 array-shape deprecation emitted by the former 1.4.4
wheel during source-window extraction. No system-wide GDAL install is assumed.

See the Phase 1 report for executed host/container checks and npm audit results.

Next.js 16.4.6 and React 19.3.1 are paired. ESLint 9.39.5 is retained because
Next's bundled import/react/accessibility plugins declare support through ESLint
9; ESLint 10 produced peer conflicts. npm labels ESLint 9 deprecated. Vitest
5.1.0 removes the critical test-tool advisories observed with the earlier version.
Seven moderate audit entries remain in the development-only TypeScript ESLint
dependency chain around minimatch. npm audit fix did not resolve them within
declared ranges. Do not force a major override without targeted compatibility
verification. The runtime dependency audit is checked separately.

