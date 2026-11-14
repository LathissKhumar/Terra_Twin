"""Database connection session management and health inspection."""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("terratwin.database")

engine = create_async_engine(
    settings.async_database_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for yielding async database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_health() -> dict[str, Any]:
    """
    Check database connectivity and verify PostGIS extension installation.
    Returns structured status dictionary.
    """
    status: dict[str, Any] = {
        "connected": False,
        "database_version": None,
        "postgis_available": False,
        "postgis_version": None,
        "error": None,
    }

    try:
        async with engine.connect() as conn:
            # Check basic connectivity and version
            res = await conn.execute(text("SELECT version();"))
            db_ver = res.scalar()
            status["connected"] = True
            status["database_version"] = db_ver

            # Check PostGIS extension
            try:
                postgis_res = await conn.execute(text("SELECT PostGIS_Version();"))
                pgis_ver = postgis_res.scalar()
                status["postgis_available"] = True
                status["postgis_version"] = pgis_ver
            except Exception as pgis_err:
                status["postgis_available"] = False
                status["postgis_version"] = None
                logger.warning("PostGIS extension check failed", error=str(pgis_err))

    except Exception as exc:
        status["connected"] = False
        status["error"] = str(exc)
        logger.warning("Database connection failed", error=str(exc))

    return status