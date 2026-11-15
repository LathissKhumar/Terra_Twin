"""Bounded PostgreSQL readiness checks and async database sessions."""

import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.schemas.health import DatabaseHealth

logger = get_logger("terratwin.database")
engine = create_async_engine(
    settings.async_database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    pool_timeout=settings.DATABASE_TIMEOUT_SECONDS,
    connect_args={
        "timeout": settings.DATABASE_TIMEOUT_SECONDS,
        "command_timeout": settings.DATABASE_TIMEOUT_SECONDS,
    },
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_database_health() -> DatabaseHealth:
    """Check PostgreSQL and PostGIS within the configured request budget."""
    result = DatabaseHealth(connected=False, postgis_available=False)
    try:
        async with asyncio.timeout(settings.DATABASE_TIMEOUT_SECONDS):
            async with engine.connect() as connection:
                result.database_version = str(
                    (await connection.execute(text("SHOW server_version"))).scalar()
                )
                result.connected = True
                installed = (
                    await connection.execute(
                        text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis')")
                    )
                ).scalar()
                if installed:
                    result.postgis_version = str(
                        (await connection.execute(text("SELECT PostGIS_Version()"))).scalar()
                    )
                    result.postgis_available = True
                else:
                    result.error = "postgis_unavailable"
    except Exception as exc:
        result.connected = False
        result.postgis_available = False
        result.error = "database_unavailable"
        logger.warning("Database readiness failed", exception_type=type(exc).__name__)
    return result
