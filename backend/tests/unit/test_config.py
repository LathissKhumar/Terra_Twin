"""Unit tests for application configuration."""

import pytest
from pydantic import SecretStr
from sqlalchemy.engine import make_url

from app.core.config import Settings


def test_cors_parsing_variations():
    """Verify CORS parsing handles both strings, lists, and comma separation."""
    s1 = Settings(CORS_ORIGINS="http://localhost:3000, http://example.com")
    assert "http://localhost:3000" in s1.CORS_ORIGINS
    assert "http://example.com" in s1.CORS_ORIGINS

    s2 = Settings(CORS_ORIGINS=["http://localhost:3000"])
    assert s2.CORS_ORIGINS == ["http://localhost:3000"]


def test_data_paths():
    """Verify data path derivations."""
    settings = Settings()
    assert settings.raw_data_dir.name == "raw"
    assert settings.manifests_dir.name == "manifests"
    assert settings.results_dir.name == "results"


def test_environment_cors(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    assert Settings().CORS_ORIGINS == ["http://localhost:3000"]
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    assert len(Settings().CORS_ORIGINS) == 2
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ValueError):
        Settings()


def test_url_credentials_and_driver():
    settings = Settings(POSTGRES_PASSWORD=SecretStr("p@ss:/%"), DATABASE_URL=None)
    assert make_url(settings.async_database_url).password == "p@ss:/%"
    settings = Settings(DATABASE_URL=SecretStr("postgresql://user:pass@localhost/db"))
    assert make_url(settings.sync_database_url).drivername == "postgresql+psycopg"
    assert make_url(settings.async_database_url).drivername == "postgresql+asyncpg"


def test_relative_storage_is_independent_of_working_directory(tmp_path, monkeypatch):
    from app.core.config import BACKEND_DIR

    monkeypatch.chdir(tmp_path)
    assert Settings(DATA_DIR="../data").DATA_DIR == (BACKEND_DIR.parent / "data").resolve()
