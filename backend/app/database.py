"""
Database configuration and session management for HomeScout.
Uses SQLAlchemy async with PostgreSQL.
"""
import os
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

# Get database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/homescout"
)

# Feature flag to enable/disable database
USE_DATABASE = os.getenv("USE_DATABASE", "false").lower() == "true"

# Lazy-loaded engine and session maker (only created when database is enabled and needed)
_engine: Optional[AsyncEngine] = None
_async_session_maker: Optional[async_sessionmaker] = None

# Base class for ORM models
Base = declarative_base()


def _get_engine() -> AsyncEngine:
    """Get or create the database engine (lazy initialization)."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            DATABASE_URL,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
            poolclass=NullPool,  # Recommended for async
            future=True
        )
    return _engine


def _get_session_maker() -> async_sessionmaker:
    """Get or create the session maker (lazy initialization)."""
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False
        )
    return _async_session_maker


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI to get an async database session.

    Usage:
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_async_session)):
            ...
    """
    async with _get_session_maker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for getting an async database session.

    Usage:
        async with get_session_context() as session:
            result = await session.execute(...)
    """
    async with _get_session_maker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database by creating all tables."""
    async with _get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


def is_database_enabled() -> bool:
    """Check if database is enabled."""
    return USE_DATABASE
