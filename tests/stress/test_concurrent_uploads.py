"""Stress: 100 concurrent POST /orders requests (TASK-045).

Uses ``httpx.AsyncClient`` + ``ASGITransport`` to drive the real ASGI app
in-process — no live server required. The acceptance criterion is that
all 100 requests return 201 and each order carries its correct tenant_id.

SQLite with ``StaticPool`` serializes writes through a single connection
so we are probing *request-handler* concurrency rather than DB scalability.
For a true cross-connection pool test point ``DATABASE_URL`` at Postgres
and re-run with ``-m stress``.
"""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from labelforge.api.v1.auth import _make_stub_jwt
from labelforge.app import app
from labelforge.db.models import Order
from labelforge.db.seed import seed_if_empty


pytestmark = pytest.mark.stress


@pytest_asyncio.fixture
async def asgi_client():
    """Boot the ASGI app in-process against an ephemeral SQLite DB."""
    from labelforge.db import seed as seed_mod, session as session_mod
    from labelforge.db.session import create_all_tables

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    orig_engine = session_mod.engine
    orig_factory = session_mod.async_session_factory
    orig_seed_factory = seed_mod.async_session_factory
    session_mod.engine = engine
    session_mod.async_session_factory = factory
    seed_mod.async_session_factory = factory

    await create_all_tables()
    await seed_if_empty()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, factory

    session_mod.engine = orig_engine
    session_mod.async_session_factory = orig_factory
    seed_mod.async_session_factory = orig_seed_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_100_concurrent_create_order_requests(asgi_client):
    ac, factory = asgi_client
    token = _make_stub_jwt("usr-admin-001", "tnt-nakoda-001", "ADMIN", "admin@nakodacraft.com")
    headers = {"Authorization": f"Bearer {token}"}

    async def one_call(i: int):
        return await ac.post(
            "/api/v1/orders",
            headers=headers,
            json={"importer_id": "IMP-ACME", "po_reference": f"PO-STRESS-{i:04d}"},
        )

    responses = await asyncio.gather(*(one_call(i) for i in range(100)))

    created_ids = []
    for r in responses:
        assert r.status_code == 201, f"got {r.status_code}: {r.text[:200]}"
        body = r.json()
        assert body["importer_id"] == "IMP-ACME"
        created_ids.append(body["id"])

    # IDs must be unique — ordering races are not allowed to collapse them.
    assert len(set(created_ids)) == 100

    # DB should reflect exactly 100 new orders under this tenant/importer.
    async with factory() as session:
        result = await session.execute(
            select(func.count(Order.id))
            .where(Order.tenant_id == "tnt-nakoda-001")
            .where(Order.importer_id == "IMP-ACME")
            .where(Order.po_number.like("PO-STRESS-%"))
        )
        count = result.scalar()
    assert count == 100


@pytest.mark.asyncio
async def test_concurrent_unauthenticated_all_rejected(asgi_client):
    ac, _ = asgi_client

    async def one_call():
        return await ac.post(
            "/api/v1/orders",
            json={"importer_id": "IMP-ACME"},
        )

    responses = await asyncio.gather(*(one_call() for _ in range(50)))
    for r in responses:
        assert r.status_code in (401, 403)
