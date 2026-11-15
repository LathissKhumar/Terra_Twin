"""Environment-backed application configuration."""

import os
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.environ.get("TERRATWIN_ENV_FILE", str(BACKEND_DIR / ".env")) or None,
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "TerraTwin"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "Planetary Analogue Discovery and Terrain Intelligence Platform"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False
    HOST: str = "127.0.0.1"
    PORT: int = Field(default=8000, ge=1, le=65535)
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = Field(default=5433, ge=1, le=65535)
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: SecretStr = SecretStr("postgres")
    POSTGRES_DB: str = "terratwin"
    DATABASE_URL: SecretStr | None = None
    DATABASE_TIMEOUT_SECONDS: float = Field(default=3, gt=0, le=30)
    DATA_DIR: Path = BACKEND_DIR.parent / "data"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            if value.strip().startswith("["):
                import json

                return json.loads(value)
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_origins(cls, value: list[str]) -> list[str]:
        for origin in value:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or origin == "*"
            ):
                raise ValueError("CORS origins must be explicit HTTP(S) origins")
        return value

    @field_validator("DATA_DIR")
    @classmethod
    def absolute_data_dir(cls, value: Path) -> Path:
        return (value if value.is_absolute() else BACKEND_DIR / value).resolve()

    def database_url(self, driver: str) -> str:
        if self.DATABASE_URL:
            url = make_url(self.DATABASE_URL.get_secret_value())
            if url.get_backend_name() != "postgresql":
                raise ValueError("Only PostgreSQL URLs are supported")
            url = url.set(drivername=driver)
        else:
            url = URL.create(
                driver,
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD.get_secret_value(),
                host=self.POSTGRES_SERVER,
                port=self.POSTGRES_PORT,
                database=self.POSTGRES_DB,
            )
        return url.render_as_string(hide_password=False)

    @property
    def async_database_url(self) -> str:
        return self.database_url("postgresql+asyncpg")

    @property
    def sync_database_url(self) -> str:
        return self.database_url("postgresql+psycopg")

    @property
    def raw_data_dir(self) -> Path:
        return self.DATA_DIR / "raw"

    @property
    def processed_data_dir(self) -> Path:
        return self.DATA_DIR / "processed"

    @property
    def derived_data_dir(self) -> Path:
        return self.DATA_DIR / "derived"

    @property
    def results_dir(self) -> Path:
        return self.DATA_DIR / "results"

    @property
    def manifests_dir(self) -> Path:
        return self.DATA_DIR / "manifests"


settings = Settings()
