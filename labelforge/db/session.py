"""Async engine and session factory."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from labelforge.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

_engine_kwargs: dict = {"echo": settings.app_debug, "future": True}
if _is_sqlite:
    # SQLite needs check_same_thread=False for async usage
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(settings.database_url, **_engine_kwargs)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency that yields an async DB session."""
    async with async_session_factory() as session:
        yield session


async def create_all_tables() -> None:
    """Create all tables (used on startup for local dev)."""
    from labelforge.db.base import Base
    from labelforge.db import models  # noqa: F401 — ensure models are registered

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
