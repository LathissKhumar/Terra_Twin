# Phase 1 API
GET / returns app/version/docs/health metadata (database-independent liveness).
GET /api/v1/health returns status, app_name, version, system and database objects.
Status is healthy (HTTP 200) only when database.connected and
database.postgis_available are true; otherwise degraded (HTTP 503). The response
has Cache-Control: no-store. Database failures expose generic error codes only.
Version fields are nullable when unavailable. No file paths or credentials appear.

The authoritative OpenAPI document is /api/v1/openapi.json, with interactive docs
at /api/v1/docs. Errors contain error.type, message, details and request path.
404/405 and validation 422 use that envelope. Unexpected failures return a generic
500. Scientific endpoints are not mounted and return 404.

