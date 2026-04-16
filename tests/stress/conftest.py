"""Stress-test fixtures: fresh in-memory engine + helpers for two tenants."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from labelforge.api.v1.auth import _make_stub_jwt
from labelforge.db.session import create_all_tables


@pytest_asyncio.fixture
async def stress_engine():
    """Disposable in-memory SQLite engine — StaticPool so the one connection
    is shared across concurrent coroutines. aiosqlite serializes access per
    connection internally, which is fine for exercising *application-level*
    concurrency (we are not trying to prove SQLite scales)."""
    from labelforge.db import session as session_mod

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    orig_engine = session_mod.engine
    orig_factory = session_mod.async_session_factory
    session_mod.engine = engine
    session_mod.async_session_factory = factory

    await create_all_tables()
    try:
        yield engine, factory
    finally:
        session_mod.engine = orig_engine
        session_mod.async_session_factory = orig_factory
        await engine.dispose()


@pytest.fixture
def two_tenants():
    """Two distinct tenant tokens for cross-isolation probing."""
    token_a = _make_stub_jwt("usr-a-001", "tnt-alpha-001", "ADMIN", "a@alpha.test")
    token_b = _make_stub_jwt("usr-b-001", "tnt-beta-002", "ADMIN", "b@beta.test")
    return {
        "a": {"tenant_id": "tnt-alpha-001", "token": token_a, "headers": {"Authorization": f"Bearer {token_a}"}},
        "b": {"tenant_id": "tnt-beta-002", "token": token_b, "headers": {"Authorization": f"Bearer {token_b}"}},
    }
