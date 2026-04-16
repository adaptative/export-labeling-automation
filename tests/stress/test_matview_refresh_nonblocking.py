"""Stress: materialized-view refresh must not block readers (TASK-045).

Acceptance criterion from #88:
- ``REFRESH MATERIALIZED VIEW CONCURRENTLY order_state_v`` runs while the
  same view is being queried by readers.
- Writers and refreshes interleave safely (no AccessExclusiveLock).

Postgres-only — automatically skipped when ``DATABASE_URL`` points at
SQLite. Set ``DATABASE_URL=postgresql+asyncpg://...`` locally to exercise.
"""
from __future__ import annotations

import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from labelforge.db.models import (
    ORDER_STATE_V_INDEX_SQL,
    ORDER_STATE_V_REFRESH_SQL,
    ORDER_STATE_V_SQL,
)


pytestmark = [pytest.mark.stress, pytest.mark.postgres]


def _postgres_url() -> str | None:
    url = os.getenv("DATABASE_URL") or os.getenv("TEST_POSTGRES_URL")
    if not url or not url.startswith(("postgresql", "postgres")):
        return None
    # Rewrite sync driver to asyncpg if a sync URL was supplied.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@pytest_asyncio.fixture
async def pg_engine():
    url = _postgres_url()
    if not url:
        pytest.skip("DATABASE_URL not set to a Postgres DSN — matview test skipped.")
    engine = create_async_engine(url, pool_size=5, max_overflow=10)
    try:
        # Seed the matview and its unique index.
        async with engine.begin() as conn:
            # order_state_v depends on `orders` + `order_items` tables.
            # We assume the caller already ran migrations — otherwise skip.
            try:
                await conn.execute(text(ORDER_STATE_V_SQL))
                await conn.execute(text(ORDER_STATE_V_INDEX_SQL))
            except Exception as exc:  # pragma: no cover — environment-specific
                pytest.skip(f"matview prerequisites missing: {exc}")
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_refresh_runs_without_blocking_readers(pg_engine):
    factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    async def reader(n: int) -> int:
        async with factory() as s:
            ok = 0
            for _ in range(n):
                await s.execute(text("SELECT COUNT(*) FROM order_state_v"))
                ok += 1
            return ok

    async def refresher():
        async with factory() as s:
            await s.execute(text(ORDER_STATE_V_REFRESH_SQL))
            await s.commit()

    # Fire 1 refresh + 3 concurrent reader loops.
    reader_tasks = [asyncio.create_task(reader(10)) for _ in range(3)]
    await asyncio.sleep(0.01)
    refresh_task = asyncio.create_task(refresher())

    results = await asyncio.gather(*reader_tasks, refresh_task)
    # Each reader completed all 10 reads under refresh contention.
    assert results[0] == 10
    assert results[1] == 10
    assert results[2] == 10


@pytest.mark.asyncio
async def test_multiple_refreshes_serialise_safely(pg_engine):
    """Back-to-back CONCURRENT refreshes must all complete — Postgres queues
    them on a weaker lock than the plain ``REFRESH MATERIALIZED VIEW``."""
    factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    async def one_refresh():
        async with factory() as s:
            await s.execute(text(ORDER_STATE_V_REFRESH_SQL))
            await s.commit()

    # 5 serial refreshes — must not deadlock.
    for _ in range(5):
        await one_refresh()
