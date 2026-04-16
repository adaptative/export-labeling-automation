"""Tests for labelforge.services.hitl.resolver (Sprint-14, TASK-028)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from labelforge.db.base import Base
from labelforge.db.models import AuditLog, HiTLMessageModel, HiTLThreadModel, Notification, Tenant
from labelforge.services.hitl import (
    InMemoryMessageRouter,
    Priority,
    ThreadResolver,
    ThreadStatus,
    priority_sla_minutes,
    set_escalation_notifier,
    set_message_router,
    set_workflow_resumer,
)
from labelforge.services.hitl.resolver import (
    AddMessageRequest,
    CreateThreadRequest,
    ThreadStateError,
    compute_sla_deadline,
)


# ── In-memory DB fixture ────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Fresh in-memory SQLite session per test with the tenant row preseeded."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add(Tenant(id="t1", name="Test tenant", slug="test"))
        await s.commit()
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def router() -> InMemoryMessageRouter:
    r = InMemoryMessageRouter()
    set_message_router(r)
    yield r
    set_message_router(None)


@pytest.fixture
def resolver(router) -> ThreadResolver:
    return ThreadResolver(router=router)


@pytest.fixture
def escalation_calls():
    """Record escalation-notifier invocations."""
    calls: list[tuple[str, str]] = []

    async def _capture(thread, reason):
        calls.append((thread.id, reason))

    set_escalation_notifier(_capture)
    yield calls
    set_escalation_notifier(None)


@pytest.fixture
def resume_calls():
    """Record workflow-resumer invocations."""
    calls: list[tuple[str, dict]] = []

    async def _capture(thread, context):
        calls.append((thread.id, context))

    set_workflow_resumer(_capture)
    yield calls
    set_workflow_resumer(None)


# ── SLA helpers ─────────────────────────────────────────────────────────────


class TestSLAHelpers:
    def test_priority_sla_minutes_expected_values(self):
        assert priority_sla_minutes("P0") == 15
        assert priority_sla_minutes("P1") == 60
        assert priority_sla_minutes("P2") == 240

    def test_unknown_priority_raises(self):
        with pytest.raises(ValueError):
            priority_sla_minutes("P9")

    def test_deadline_is_now_plus_sla(self):
        anchor = datetime(2026, 1, 1, tzinfo=timezone.utc)
        d = compute_sla_deadline("P1", now=anchor)
        assert (d - anchor).total_seconds() == 60 * 60


# ── create_thread ───────────────────────────────────────────────────────────


class TestCreateThread:
    @pytest.mark.asyncio
    async def test_persists_thread_and_audit(self, session, resolver):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion-agent", priority="P1",
        ))
        assert thread.id
        assert thread.status == "OPEN"
        assert thread.priority == "P1"
        assert thread.sla_deadline is not None

        audits = (await session.execute(
            select(AuditLog).where(AuditLog.action == "hitl_thread_created")
        )).scalars().all()
        assert len(audits) == 1
        assert audits[0].resource_id == thread.id
        assert audits[0].details.get("priority") == "P1"

    @pytest.mark.asyncio
    async def test_initial_message_is_persisted_and_broadcast(self, session, resolver, router):
        sub = router.subscribe("_placeholder")  # bind before any publish
        await sub.unsubscribe()

        # Subscribe to the real thread id once created requires discovery;
        # instead subscribe broadly by publishing then inspecting the model.
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion-agent", priority="P0",
            initial_message="Net weight mismatch",
            context={"po": 0.75, "pi": 0.80},
        ))

        msgs = (await session.execute(
            select(HiTLMessageModel).where(HiTLMessageModel.thread_id == thread.id)
        )).scalars().all()
        assert len(msgs) == 1
        assert msgs[0].content == "Net weight mismatch"
        assert msgs[0].sender_type == "agent"

    @pytest.mark.asyncio
    async def test_unknown_priority_rejected(self, session, resolver):
        with pytest.raises(ValueError):
            await resolver.create_thread(session, CreateThreadRequest(
                tenant_id="t1", order_id="ORD-1", item_no="A1",
                agent_id="fusion-agent", priority="P99",
            ))

    @pytest.mark.asyncio
    async def test_broadcasts_status_update(self, session, resolver, router):
        # Pre-subscribe by generating ID ourselves? The resolver generates it.
        # Alternative: let create_thread run, verify via new subscriber.
        # Instead, capture publish by swapping router with a recording one.
        published: list[dict] = []

        class _RecordRouter:
            async def publish(self, thread_id, envelope):
                published.append(envelope)

            def subscribe(self, thread_id):  # pragma: no cover — unused
                raise NotImplementedError

            async def aclose(self):  # pragma: no cover
                pass

        set_message_router(_RecordRouter())
        try:
            r = ThreadResolver()
            await r.create_thread(session, CreateThreadRequest(
                tenant_id="t1", order_id="ORD-1", item_no="A1",
                agent_id="fusion", priority="P2",
                initial_message="Hello",
            ))
        finally:
            set_message_router(router)  # restore

        types = [e["type"] for e in published]
        assert "status_update" in types
        assert "agent_message" in types


# ── add_message + state transitions ─────────────────────────────────────────


class TestAddMessage:
    @pytest.mark.asyncio
    async def test_human_reply_transitions_open_to_in_progress(self, session, resolver):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion", priority="P2",
        ))
        assert thread.status == "OPEN"
        await resolver.add_message(session, AddMessageRequest(
            tenant_id="t1", thread_id=thread.id,
            sender_type="human", content="Looking into it",
            actor="usr-ops-001",
        ))
        refreshed = (await session.execute(
            select(HiTLThreadModel).where(HiTLThreadModel.id == thread.id)
        )).scalar_one()
        assert refreshed.status == "IN_PROGRESS"

    @pytest.mark.asyncio
    async def test_agent_reply_does_not_transition(self, session, resolver):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion", priority="P2",
        ))
        await resolver.add_message(session, AddMessageRequest(
            tenant_id="t1", thread_id=thread.id,
            sender_type="agent", content="Probing",
        ))
        refreshed = (await session.execute(
            select(HiTLThreadModel).where(HiTLThreadModel.id == thread.id)
        )).scalar_one()
        assert refreshed.status == "OPEN"

    @pytest.mark.asyncio
    async def test_message_to_unknown_thread_raises(self, session, resolver):
        with pytest.raises(ThreadStateError):
            await resolver.add_message(session, AddMessageRequest(
                tenant_id="t1", thread_id="does-not-exist",
                sender_type="human", content="hello",
            ))

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, session, resolver):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion", priority="P2",
        ))
        with pytest.raises(ThreadStateError):
            await resolver.add_message(session, AddMessageRequest(
                tenant_id="other-tenant", thread_id=thread.id,
                sender_type="human", content="hello",
            ))


# ── resolve ─────────────────────────────────────────────────────────────────


class TestResolveThread:
    @pytest.mark.asyncio
    async def test_resolve_sets_status_and_writes_audit(
        self, session, resolver, resume_calls,
    ):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion", priority="P1",
        ))
        resolved = await resolver.resolve_thread(
            session, tenant_id="t1", thread_id=thread.id,
            actor="usr-admin-001", resolution_note="Confirmed net weight is 0.80",
        )
        assert resolved.status == "RESOLVED"
        assert resolved.resolved_at is not None

        audits = (await session.execute(
            select(AuditLog).where(
                AuditLog.action == "hitl_thread_resolved",
                AuditLog.resource_id == thread.id,
            )
        )).scalars().all()
        assert len(audits) == 1
        assert audits[0].actor == "usr-admin-001"

    @pytest.mark.asyncio
    async def test_resolve_calls_workflow_resumer(
        self, session, resolver, resume_calls,
    ):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion", priority="P1",
        ))
        await resolver.resolve_thread(
            session, tenant_id="t1", thread_id=thread.id, actor="u",
            resume_context={"decision": "net_weight=0.80"},
        )
        assert len(resume_calls) == 1
        assert resume_calls[0][0] == thread.id
        assert resume_calls[0][1] == {"decision": "net_weight=0.80"}

    @pytest.mark.asyncio
    async def test_resolve_twice_rejected(self, session, resolver):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion", priority="P2",
        ))
        await resolver.resolve_thread(
            session, tenant_id="t1", thread_id=thread.id, actor="u",
        )
        with pytest.raises(ThreadStateError):
            await resolver.resolve_thread(
                session, tenant_id="t1", thread_id=thread.id, actor="u",
            )

    @pytest.mark.asyncio
    async def test_cannot_add_message_after_resolve(self, session, resolver):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion", priority="P2",
        ))
        await resolver.resolve_thread(
            session, tenant_id="t1", thread_id=thread.id, actor="u",
        )
        with pytest.raises(ThreadStateError):
            await resolver.add_message(session, AddMessageRequest(
                tenant_id="t1", thread_id=thread.id,
                sender_type="human", content="late reply",
            ))


# ── escalate ────────────────────────────────────────────────────────────────


class TestEscalateThread:
    @pytest.mark.asyncio
    async def test_escalate_sets_status_and_notifies(
        self, session, resolver, escalation_calls,
    ):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion", priority="P0",
        ))
        escalated = await resolver.escalate_thread(
            session, tenant_id="t1", thread_id=thread.id,
            reason="No owner for 30 min", actor="u",
        )
        assert escalated.status == "ESCALATED"
        assert len(escalation_calls) == 1
        assert escalation_calls[0] == (thread.id, "No owner for 30 min")

    @pytest.mark.asyncio
    async def test_escalate_writes_notification_row(self, session, resolver):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion", priority="P1",
        ))
        await resolver.escalate_thread(
            session, tenant_id="t1", thread_id=thread.id,
            reason="Missing SKU mapping", actor="u",
        )
        notifs = (await session.execute(
            select(Notification).where(Notification.type == "hitl_escalation")
        )).scalars().all()
        assert len(notifs) == 1
        assert notifs[0].level == "warning"
        assert notifs[0].order_id == "ORD-1"

    @pytest.mark.asyncio
    async def test_escalate_twice_rejected(self, session, resolver):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion", priority="P2",
        ))
        await resolver.escalate_thread(
            session, tenant_id="t1", thread_id=thread.id,
            reason="x", actor="u",
        )
        with pytest.raises(ThreadStateError):
            await resolver.escalate_thread(
                session, tenant_id="t1", thread_id=thread.id,
                reason="x", actor="u",
            )


# ── option-select ───────────────────────────────────────────────────────────


class TestOptionSelect:
    @pytest.mark.asyncio
    async def test_records_message_and_transitions(self, session, resolver):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion", priority="P2",
        ))
        msg = await resolver.record_option_select(
            session, tenant_id="t1", thread_id=thread.id,
            option_index=1, option_value="Use PI value (0.80)",
            actor="usr-ops-001",
        )
        assert msg.sender_type == "human"
        assert msg.context["option_index"] == 1
        assert msg.context["option_value"] == "Use PI value (0.80)"

        refreshed = (await session.execute(
            select(HiTLThreadModel).where(HiTLThreadModel.id == thread.id)
        )).scalar_one()
        assert refreshed.status == "IN_PROGRESS"

    @pytest.mark.asyncio
    async def test_option_select_blocked_on_resolved(self, session, resolver):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion", priority="P2",
        ))
        await resolver.resolve_thread(
            session, tenant_id="t1", thread_id=thread.id, actor="u",
        )
        with pytest.raises(ThreadStateError):
            await resolver.record_option_select(
                session, tenant_id="t1", thread_id=thread.id,
                option_index=0,
            )


# ── Router integration — end-to-end fan-out ─────────────────────────────────


class TestRouterIntegration:
    @pytest.mark.asyncio
    async def test_add_message_publishes_to_subscriber(self, session, resolver, router):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion", priority="P2",
        ))
        sub = router.subscribe(thread.id)
        await resolver.add_message(session, AddMessageRequest(
            tenant_id="t1", thread_id=thread.id,
            sender_type="human", content="Got it",
        ))
        # First envelope is the human_message itself; the status_update
        # (OPEN→IN_PROGRESS) follows. Either ordering is acceptable, but
        # both MUST appear.
        seen = []
        for _ in range(2):
            seen.append(
                (await asyncio.wait_for(sub.__anext__(), timeout=0.5))["type"]
            )
        assert "human_message" in seen
        assert "status_update" in seen
        await sub.unsubscribe()

    @pytest.mark.asyncio
    async def test_resolve_broadcasts_thread_resolved(self, session, resolver, router):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion", priority="P2",
        ))
        sub = router.subscribe(thread.id)
        await resolver.resolve_thread(
            session, tenant_id="t1", thread_id=thread.id, actor="u",
        )
        env = await asyncio.wait_for(sub.__anext__(), timeout=0.5)
        assert env["type"] == "thread_resolved"
        assert env["payload"]["status"] == "RESOLVED"
        await sub.unsubscribe()

    @pytest.mark.asyncio
    async def test_escalate_broadcasts_escalation(self, session, resolver, router):
        thread = await resolver.create_thread(session, CreateThreadRequest(
            tenant_id="t1", order_id="ORD-1", item_no="A1",
            agent_id="fusion", priority="P1",
        ))
        sub = router.subscribe(thread.id)
        await resolver.escalate_thread(
            session, tenant_id="t1", thread_id=thread.id,
            reason="Critical", actor="u",
        )
        env = await asyncio.wait_for(sub.__anext__(), timeout=0.5)
        assert env["type"] == "escalation"
        assert env["payload"]["reason"] == "Critical"
        await sub.unsubscribe()
