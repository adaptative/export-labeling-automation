"""Advance-endpoint self-heal: HUMAN_BLOCKED → last_successful_state
once every linked HiTL thread is resolved.

Covers the #181 regression — the pipeline would pin an order at
HUMAN_BLOCKED indefinitely even after an operator had resolved every
thread, because ``/orders/{id}/advance`` only runs ``_STAGE_PLAN``
transitions from active pipeline states (FUSED, COMPLIANCE_EVAL, …).
"""
from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from labelforge.api.v1.orders import _rescue_resolved_items
from labelforge.db import session as _session_mod
from labelforge.db.base import Base
from labelforge.db.models import (
    HiTLThreadModel,
    Importer,
    Order,
    OrderItemModel,
    Tenant,
)


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    f = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield f
    await engine.dispose()


@pytest_asyncio.fixture
async def order_with_blocked_items(factory, monkeypatch):
    """Seed a tenant + importer + order + 2 HUMAN_BLOCKED items.

    Each item carries the ``blocked_at_stage`` / ``last_successful_state``
    breadcrumbs the pipeline writes. One item has a single RESOLVED
    thread; the other has one RESOLVED and one OPEN — so the helper
    must rescue the first and leave the second alone.
    """
    monkeypatch.setattr(_session_mod, "async_session_factory", factory)
    async with factory() as s:
        s.add(Tenant(id="t1", name="Test", slug=f"t-{uuid4().hex[:6]}"))
        s.add(Importer(id="IMP-1", tenant_id="t1", name="Acme", code="ACME"))
        s.add(Order(id="ORD-X", tenant_id="t1", importer_id="IMP-1"))
        for item_no, extra_thread in (("A1", False), ("A2", True)):
            s.add(OrderItemModel(
                id=str(uuid4()),
                order_id="ORD-X",
                tenant_id="t1",
                item_no=item_no,
                state="HUMAN_BLOCKED",
                data={
                    "item_no": item_no,
                    "blocked_at_stage": "VALIDATED",
                    "blocked_reason": "required fields missing",
                    "last_successful_state": "COMPOSED",
                },
            ))
            s.add(HiTLThreadModel(
                id=str(uuid4()),
                tenant_id="t1",
                order_id="ORD-X",
                item_no=item_no,
                agent_id="validate_output_activity",
                priority="P2",
                status="RESOLVED",
            ))
            if extra_thread:
                s.add(HiTLThreadModel(
                    id=str(uuid4()),
                    tenant_id="t1",
                    order_id="ORD-X",
                    item_no=item_no,
                    agent_id="compliance_eval_activity",
                    priority="P2",
                    status="OPEN",
                ))
        await s.commit()

    return factory


async def _load_order(sess: AsyncSession, order_id: str) -> Order:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    stmt = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
    )
    order = (await sess.execute(stmt)).scalar_one_or_none()
    assert order is not None, f"order {order_id!r} not seeded"
    return order


# ── The self-heal helper ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rescue_resolved_items_restores_last_successful_state(
    order_with_blocked_items,
):
    """Item A1 has only a RESOLVED thread, so its state flips back to
    ``last_successful_state`` (COMPOSED) and the block markers clear.
    Item A2 still has an OPEN thread and must stay HUMAN_BLOCKED."""
    factory = order_with_blocked_items

    async with factory() as sess:
        order = await _load_order(sess, "ORD-X")
        rescued = await _rescue_resolved_items(
            sess, tenant_id="t1", order=order,
        )
        await sess.commit()
    assert rescued == 1

    # Re-read in a fresh session to see the committed state.
    async with factory() as sess:
        order2 = await _load_order(sess, "ORD-X")
        by_no = {it.item_no: it for it in order2.items}

    a1 = by_no["A1"]
    assert a1.state == "COMPOSED"
    assert "blocked_at_stage" not in (a1.data or {})
    assert "blocked_reason" not in (a1.data or {})

    a2 = by_no["A2"]
    assert a2.state == "HUMAN_BLOCKED"
    # Still blocked, so breadcrumbs are intact.
    assert (a2.data or {}).get("blocked_at_stage") == "VALIDATED"


@pytest.mark.asyncio
async def test_rescue_with_missing_last_successful_state_falls_back_to_fused(
    factory, monkeypatch,
):
    """Defensive — an item without ``last_successful_state`` (pipeline
    ran before the breadcrumb wiring landed) should still unblock
    rather than staying stuck forever. FUSED is the earliest possible
    resume point in the advance pipeline."""
    monkeypatch.setattr(_session_mod, "async_session_factory", factory)
    async with factory() as s:
        s.add(Tenant(id="t1", name="Test", slug=f"t-{uuid4().hex[:6]}"))
        s.add(Importer(id="IMP-1", tenant_id="t1", name="Acme", code="ACME"))
        s.add(Order(id="ORD-Y", tenant_id="t1", importer_id="IMP-1"))
        s.add(OrderItemModel(
            id=str(uuid4()),
            order_id="ORD-Y",
            tenant_id="t1",
            item_no="legacy",
            state="HUMAN_BLOCKED",
            data={"item_no": "legacy"},  # no breadcrumbs
        ))
        s.add(HiTLThreadModel(
            id=str(uuid4()),
            tenant_id="t1",
            order_id="ORD-Y",
            item_no="legacy",
            agent_id="validate_output_activity",
            priority="P2",
            status="RESOLVED",
        ))
        await s.commit()

    async with factory() as sess:
        order = await _load_order(sess, "ORD-Y")
        rescued = await _rescue_resolved_items(
            sess, tenant_id="t1", order=order,
        )
        await sess.commit()
    assert rescued == 1

    async with factory() as sess:
        order2 = await _load_order(sess, "ORD-Y")
        assert order2.items[0].state == "FUSED"
