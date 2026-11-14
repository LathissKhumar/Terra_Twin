import os

import pytest

from app.database.session import check_database_health, engine


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1 for live database"
)
async def test_postgresql_and_postgis():
    try:
        health = await check_database_health()
        assert health.connected, health.error
        assert health.postgis_available
        assert health.database_version
        assert health.postgis_version
    finally:
        await engine.dispose()
