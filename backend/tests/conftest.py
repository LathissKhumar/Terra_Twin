"""Keep unit/API tests independent of developer credentials and running services."""

import os

os.environ["ENVIRONMENT"] = "test"
os.environ["TERRATWIN_ENV_FILE"] = ""
os.environ["PROJECT_NAME"] = "TerraTwin"
os.environ["VERSION"] = "0.1.0"
os.environ["API_V1_STR"] = "/api/v1"
os.environ["DEBUG"] = "false"
os.environ["HOST"] = "127.0.0.1"
os.environ["PORT"] = "8000"
os.environ["DESCRIPTION"] = "TerraTwin test configuration"
os.environ["CORS_ORIGINS"] = "http://localhost:3000,http://127.0.0.1:3000"
os.environ.pop("DATA_DIR", None)
os.environ.pop("DATABASE_TIMEOUT_SECONDS", None)
if os.environ.get("RUN_DB_TESTS") != "1":
    for name in (
        "DATABASE_URL",
        "POSTGRES_SERVER",
        "POSTGRES_PORT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
    ):
        os.environ.pop(name, None)
