import asyncio
from unittest.mock import MagicMock

from app.database import session


async def test_connection_exception_is_sanitized(monkeypatch):
    fake = MagicMock()
    fake.connect.side_effect = RuntimeError("secret password /private/file")
    monkeypatch.setattr(session, "engine", fake)
    result = await session.check_database_health()
    assert not result.connected
    assert result.error == "database_unavailable"
    assert "secret" not in result.model_dump_json()


async def test_probe_timeout(monkeypatch):
    class Slow:
        async def __aenter__(self):
            await asyncio.sleep(10)

        async def __aexit__(self, *args):
            pass

    fake = MagicMock()
    fake.connect.return_value = Slow()
    monkeypatch.setattr(session, "engine", fake)
    monkeypatch.setattr(session.settings, "DATABASE_TIMEOUT_SECONDS", 0.01)
    result = await asyncio.wait_for(session.check_database_health(), timeout=1)
    assert result.error == "database_unavailable"
