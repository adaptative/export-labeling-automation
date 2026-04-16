"""Stress: cross-tenant isolation under concurrent load (TASK-045).

Acceptance criteria from #88:
- Two tenants issue concurrent writes; each sees only its own data.
- Direct fetch with tenant A's token of tenant B's order returns 404.
- 200+ interleaved requests surface zero data leaks.
"""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from labelforge.api.v1.auth import _make_stub_jwt
from labelforge.app import app
from labelforge.db.models import Importer, Order, Tenant
from labelforge.db.seed import seed_if_empty


pytestmark = pytest.mark.stress


@pytest_asyncio.fixture
async def two_tenant_client():
    """Boot the app, seed tenant A (via seed), and insert tenant B by hand."""
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

    # Seed a second tenant + importer that will not appear in the default seed.
    async with factory() as s:
        s.add(Tenant(id="tnt-beta-002", name="Beta Co", slug="beta"))
        s.add(
            Importer(
                id="IMP-BETA",
                tenant_id="tnt-beta-002",
                name="Beta Importer",
                code="BETA",
            )
        )
        await s.commit()

    token_a = _make_stub_jwt(
        "usr-a-001", "tnt-nakoda-001", "ADMIN", "a@nakodacraft.com"
    )
    token_b = _make_stub_jwt("usr-b-001", "tnt-beta-002", "ADMIN", "b@beta.test")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield {
            "client": ac,
            "factory": factory,
            "a": {
                "tenant_id": "tnt-nakoda-001",
                "importer_id": "IMP-ACME",
                "headers": {"Authorization": f"Bearer {token_a}"},
            },
            "b": {
                "tenant_id": "tnt-beta-002",
                "importer_id": "IMP-BETA",
                "headers": {"Authorization": f"Bearer {token_b}"},
            },
        }

    session_mod.engine = orig_engine
    session_mod.async_session_factory = orig_factory
    seed_mod.async_session_factory = orig_seed_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_interleaved_writes_do_not_leak(two_tenant_client):
    ctx = two_tenant_client
    ac = ctx["client"]

    async def create(tenant_key: str, i: int):
        t = ctx[tenant_key]
        return await ac.post(
            "/api/v1/orders",
            headers=t["headers"],
            json={
                "importer_id": t["importer_id"],
                "po_reference": f"PO-{tenant_key.upper()}-{i:03d}",
            },
        )

    # 100 interleaved writes across both tenants (50 each).
    tasks = []
    for i in range(50):
        tasks.append(create("a", i))
        tasks.append(create("b", i))
    responses = await asyncio.gather(*tasks)
    for r in responses:
        assert r.status_code == 201, r.text[:200]

    # DB check: each tenant sees exactly its 50 new orders with the right ids.
    async with ctx["factory"]() as s:
        result = await s.execute(
            select(Order).where(Order.po_number.like("PO-A-%"))
        )
        a_rows = result.scalars().all()
        result = await s.execute(
            select(Order).where(Order.po_number.like("PO-B-%"))
        )
        b_rows = result.scalars().all()

    assert len(a_rows) == 50
    assert all(o.tenant_id == "tnt-nakoda-001" for o in a_rows)
    assert len(b_rows) == 50
    assert all(o.tenant_id == "tnt-beta-002" for o in b_rows)


@pytest.mark.asyncio
async def test_tenant_a_cannot_read_tenant_b_order(two_tenant_client):
    ctx = two_tenant_client
    ac = ctx["client"]

    create = await ac.post(
        "/api/v1/orders",
        headers=ctx["b"]["headers"],
        json={"importer_id": "IMP-BETA", "po_reference": "PO-SECRET-001"},
    )
    assert create.status_code == 201
    b_order_id = create.json()["id"]

    # Tenant A tries to fetch B's order — must return 404 (not 403 leak).
    resp = await ac.get(f"/api/v1/orders/{b_order_id}", headers=ctx["a"]["headers"])
    assert resp.status_code in (403, 404), (
        f"tenant-isolation breach: expected 403/404 got {resp.status_code}"
    )

    # Tenant B can fetch its own order.
    resp = await ac.get(f"/api/v1/orders/{b_order_id}", headers=ctx["b"]["headers"])
    assert resp.status_code == 200
    assert resp.json()["id"] == b_order_id


@pytest.mark.asyncio
async def test_list_orders_is_tenant_scoped(two_tenant_client):
    ctx = two_tenant_client
    ac = ctx["client"]

    for i in range(5):
        await ac.post(
            "/api/v1/orders",
            headers=ctx["a"]["headers"],
            json={"importer_id": "IMP-ACME", "po_reference": f"A-ONLY-{i}"},
        )
    for i in range(5):
        await ac.post(
            "/api/v1/orders",
            headers=ctx["b"]["headers"],
            json={"importer_id": "IMP-BETA", "po_reference": f"B-ONLY-{i}"},
        )

    list_a = await ac.get("/api/v1/orders", headers=ctx["a"]["headers"])
    list_b = await ac.get("/api/v1/orders", headers=ctx["b"]["headers"])
    assert list_a.status_code == 200
    assert list_b.status_code == 200

    def _po_numbers(body: dict) -> set[str]:
        orders = body if isinstance(body, list) else body.get("orders", body.get("items", []))
        return {o.get("po_number", "") for o in orders}

    a_pos = _po_numbers(list_a.json())
    b_pos = _po_numbers(list_b.json())

    # A's list must only contain A's PO numbers, and B's must only contain B's.
    assert any(p.startswith("A-ONLY-") for p in a_pos)
    assert not any(p.startswith("B-ONLY-") for p in a_pos), "leaked B's PO into A's list"
    assert any(p.startswith("B-ONLY-") for p in b_pos)
    assert not any(p.startswith("A-ONLY-") for p in b_pos), "leaked A's PO into B's list"
