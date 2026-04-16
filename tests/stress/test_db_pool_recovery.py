"""Stress: DB connection-pool recovery after churn (TASK-045).

Acceptance criteria from #88:
- Pool returns connections after cycling through pool_size × N requests.
- No "QueuePool limit overflow" under sustained load when ``max_overflow``
  respected.
- Sessions that raised mid-transaction are rolled back and recycled.
"""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


pytestmark = pytest.mark.stress


@pytest_asyncio.fixture
async def pooled_engine():
    """Real SQLAlchemy pool (no StaticPool) against an in-memory SQLite file.

    Using ``aiosqlite`` with a shared URI lets multiple connections see the
    same database — the default tuneable AsyncAdaptedQueuePool (pool_size=3,
    max_overflow=5) exercises real pool behaviour.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true",
        pool_size=3,
        max_overflow=5,
        pool_timeout=5,
        pool_pre_ping=True,
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Create a tiny table to exercise.
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE IF NOT EXISTS probe (id INTEGER PRIMARY KEY)"))
        await conn.execute(text("DELETE FROM probe"))

    try:
        yield engine, factory
    finally:
        await engine.dispose()


class TestPoolRecovery:
    @pytest.mark.asyncio
    async def test_many_short_sessions_recycle(self, pooled_engine):
        engine, factory = pooled_engine

        async def one_op(i: int) -> int:
            async with factory() as s:
                await s.execute(text("INSERT INTO probe (id) VALUES (:i)"), {"i": i})
                await s.commit()
                result = await s.execute(text("SELECT COUNT(*) FROM probe"))
                return int(result.scalar() or 0)

        results = []
        # 200 sequential ops far exceed pool_size+max_overflow; every session
        # must complete because the pool recycles connections between them.
        for i in range(200):
            results.append(await one_op(i))
        assert results[-1] == 200

    @pytest.mark.asyncio
    async def test_failed_transaction_does_not_leak_connection(self, pooled_engine):
        engine, factory = pooled_engine

        async def bad_op():
            async with factory() as s:
                try:
                    await s.execute(text("INSERT INTO probe (id) VALUES (1)"))  # dup PK second time
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise

        # First succeeds; second fails on PK collision. Repeat 20× to burn
        # through any leaked connections.
        async with factory() as s:
            await s.execute(text("DELETE FROM probe"))
            await s.commit()
        await bad_op()  # seeds row id=1
        for _ in range(20):
            with pytest.raises(Exception):
                await bad_op()

        # Pool should still have capacity — a healthy read must succeed.
        async with factory() as s:
            result = await s.execute(text("SELECT COUNT(*) FROM probe"))
            assert int(result.scalar() or 0) == 1

    @pytest.mark.asyncio
    async def test_concurrent_sessions_within_pool_limit(self, pooled_engine):
        engine, factory = pooled_engine

        async def one():
            async with factory() as s:
                await s.execute(text("SELECT 1"))
                # Hold the connection briefly to force overlap.
                await asyncio.sleep(0.005)
                await s.execute(text("SELECT 1"))

        # 6 concurrent sessions — under max_overflow (5) + pool_size (3) = 8.
        await asyncio.gather(*(one() for _ in range(6)))

    @pytest.mark.asyncio
    async def test_pool_dispose_closes_cleanly(self, pooled_engine):
        engine, factory = pooled_engine
        async with factory() as s:
            await s.execute(text("SELECT 1"))
        # dispose is idempotent.
        await engine.dispose()
        await engine.dispose()
