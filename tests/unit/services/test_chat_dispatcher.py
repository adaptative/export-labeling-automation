"""Tests for labelforge.services.hitl.chat_dispatcher.

The dispatcher is the async glue between a human's reply on a HITL
thread and the per-agent chat handler. These tests exercise it end-to-end
against an in-memory SQLite DB: the dispatcher reads real rows, calls a
stubbed handler, writes real agent messages back through the resolver,
and (for the resolved=True path) invokes the auto-advance hook.

Tests swap out a few module-level singletons:

* ``labelforge.db.session.async_session_factory`` — the dispatcher opens
  its own sessions rather than accept one as a parameter, so we
  monkeypatch the module attribute to point at our in-memory factory.
* ``labelforge.agents.chat._REGISTRY`` — tests register a fake
  :class:`AgentChatHandler` whose ``respond()`` returns a canned reply.
* ``labelforge.services.hitl.chat_dispatcher._auto_advance`` — captured
  via ``set_auto_advance_hook`` so we can assert the hook fires on
  resolved=True.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from labelforge.agents.chat import (
    AgentChatHandler,
    ChatContext,
    ChatReply,
    clear_registry,
    register_chat_handler,
)
from labelforge.db import session as _session_mod
from labelforge.db.base import Base
from labelforge.db.models import (
    ComplianceRule,
    HiTLMessageModel,
    HiTLThreadModel,
    Importer,
    ImporterDocument,
    ImporterProfileModel,
    Order,
    OrderItemModel,
    Tenant,
    WarningLabel,
)
from labelforge.services.hitl import (
    InMemoryMessageRouter,
    set_message_router,
)
from labelforge.services.hitl.chat_dispatcher import (
    MAX_AGENT_TURNS,
    dispatch_on_human_message,
    set_auto_advance_hook,
)


# ── Fake handler ────────────────────────────────────────────────────────────


class _FakeHandler(AgentChatHandler):
    """Handler whose ``respond()`` returns a canned :class:`ChatReply`.

    Records every invocation so tests can assert the dispatcher passes
    the right :class:`ChatContext`.
    """

    agent_id = "fake"
    patch_allowlist = ("*",)  # allow any patch in tests

    def __init__(self, reply: ChatReply, *, agent_id: str = "fake") -> None:
        super().__init__()
        self.agent_id = agent_id
        self._reply = reply
        self.calls: List[ChatContext] = []

    async def respond(self, ctx: ChatContext) -> ChatReply:  # type: ignore[override]
        self.calls.append(ctx)
        return self._reply


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def engine_and_factory():
    """Fresh in-memory SQLite engine + sessionmaker per test."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False,
    )
    yield engine, factory
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded(engine_and_factory, monkeypatch):
    """Seed tenant/importer/order/item and repoint async_session_factory.

    Returns a dict with the ids the tests need. The dispatcher uses
    ``labelforge.db.session.async_session_factory`` directly, so we
    monkeypatch that module attribute to the test factory. Tests that
    need ad-hoc writes use the returned factory.
    """
    engine, factory = engine_and_factory
    monkeypatch.setattr(_session_mod, "async_session_factory", factory)

    order_id = f"ord-{uuid4().hex[:8]}"
    item_no = "A1"
    importer_id = f"imp-{uuid4().hex[:8]}"

    async with factory() as s:
        s.add(Tenant(id="t1", name="Test", slug=f"test-{uuid4().hex[:6]}"))
        s.add(Importer(id=importer_id, tenant_id="t1", name="Acme", code="ACME"))
        s.add(Order(id=order_id, tenant_id="t1", importer_id=importer_id))
        s.add(OrderItemModel(
            id=str(uuid4()),
            order_id=order_id,
            tenant_id="t1",
            item_no=item_no,
            state="CREATED",
            data={"upc": "012345", "blocked_reason": "missing country_of_origin"},
        ))
        await s.commit()

    return {
        "factory": factory,
        "order_id": order_id,
        "item_no": item_no,
    }


@pytest.fixture
def router():
    r = InMemoryMessageRouter()
    set_message_router(r)
    yield r
    set_message_router(None)


@pytest.fixture
def registry():
    """Clear the chat-handler registry around each test."""
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def auto_advance_calls():
    """Capture auto-advance hook invocations."""
    calls: List[Tuple[str, str]] = []

    async def _capture(tenant_id: str, order_id: str) -> None:
        calls.append((tenant_id, order_id))

    set_auto_advance_hook(_capture)
    yield calls
    set_auto_advance_hook(None)  # restore default no-op


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _open_thread(
    factory,
    *,
    order_id: str,
    item_no: str,
    agent_id: str = "fake",
    extra_messages: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Create a HITL thread with the opening agent message + seed history."""
    thread_id = str(uuid4())
    async with factory() as s:
        s.add(HiTLThreadModel(
            id=thread_id,
            tenant_id="t1",
            order_id=order_id,
            item_no=item_no,
            agent_id=agent_id,
            priority="P1",
            status="IN_PROGRESS",
        ))
        # Opening agent message carrying pause_context
        s.add(HiTLMessageModel(
            id=str(uuid4()),
            thread_id=thread_id,
            tenant_id="t1",
            sender_type="agent",
            content="I need the country of origin to proceed.",
            context={"reason": "missing country_of_origin", "stage": "fuse"},
        ))
        for m in extra_messages or []:
            s.add(HiTLMessageModel(
                id=str(uuid4()),
                thread_id=thread_id,
                tenant_id="t1",
                sender_type=m["sender_type"],
                content=m["content"],
                context=m.get("context"),
            ))
        await s.commit()
    return thread_id


async def _fetch_messages(factory, thread_id: str) -> List[HiTLMessageModel]:
    async with factory() as s:
        result = await s.execute(
            select(HiTLMessageModel)
            .where(HiTLMessageModel.thread_id == thread_id)
            .order_by(HiTLMessageModel.created_at)
        )
        return list(result.scalars().all())


async def _fetch_thread(factory, thread_id: str) -> Optional[HiTLThreadModel]:
    async with factory() as s:
        result = await s.execute(
            select(HiTLThreadModel).where(HiTLThreadModel.id == thread_id)
        )
        return result.scalar_one_or_none()


async def _fetch_item(factory, order_id: str, item_no: str) -> Optional[OrderItemModel]:
    async with factory() as s:
        result = await s.execute(
            select(OrderItemModel).where(
                OrderItemModel.order_id == order_id,
                OrderItemModel.item_no == item_no,
            )
        )
        return result.scalar_one_or_none()


# ── Happy path ──────────────────────────────────────────────────────────────


class TestDispatcherHappyPath:
    @pytest.mark.asyncio
    async def test_plain_reply_posts_agent_message(
        self, seeded, router, registry,
    ):
        register_chat_handler(_FakeHandler(ChatReply(text="Got it, thanks.")))
        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            extra_messages=[
                {"sender_type": "human", "content": "The country is China."},
            ],
        )
        reply = await dispatch_on_human_message(thread_id, "t1")
        assert reply is not None
        assert reply.text == "Got it, thanks."

        msgs = await _fetch_messages(seeded["factory"], thread_id)
        # opener + human + new agent reply
        assert len(msgs) == 3
        assert msgs[-1].sender_type == "agent"
        assert msgs[-1].content == "Got it, thanks."

    @pytest.mark.asyncio
    async def test_handler_receives_pause_context_and_history(
        self, seeded, router, registry,
    ):
        handler = _FakeHandler(ChatReply(text="ok"))
        register_chat_handler(handler)
        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            extra_messages=[
                {"sender_type": "human", "content": "Hello?"},
            ],
        )
        await dispatch_on_human_message(thread_id, "t1")
        assert len(handler.calls) == 1
        ctx = handler.calls[0]
        assert ctx.order_id == seeded["order_id"]
        assert ctx.item_no == seeded["item_no"]
        assert ctx.agent_id == "fake"
        # Pause context sourced from the opening agent message
        assert ctx.pause_context.get("reason") == "missing country_of_origin"
        # History includes both the agent opener and the human turn
        roles = [m.role for m in ctx.messages]
        assert roles == ["agent", "human"]
        assert ctx.item_data.get("upc") == "012345"


# ── Tool-call: patches applied ──────────────────────────────────────────────


class TestDispatcherPatches:
    @pytest.mark.asyncio
    async def test_patches_applied_to_item_data(
        self, seeded, router, registry,
    ):
        register_chat_handler(_FakeHandler(ChatReply(
            text="Setting country to CN.",
            patches={"country_of_origin": "CN"},
        )))
        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            extra_messages=[
                {"sender_type": "human", "content": "It's China."},
            ],
        )
        await dispatch_on_human_message(thread_id, "t1")

        item = await _fetch_item(
            seeded["factory"], seeded["order_id"], seeded["item_no"],
        )
        assert item is not None
        assert item.data["country_of_origin"] == "CN"
        # blocked_reason is cleared so the next advance doesn't re-raise
        assert "blocked_reason" not in item.data
        # Pre-existing fields survive
        assert item.data["upc"] == "012345"

    @pytest.mark.asyncio
    async def test_dotted_key_patch_nests(
        self, seeded, router, registry,
    ):
        register_chat_handler(_FakeHandler(ChatReply(
            text="Updating fused subtree.",
            patches={"fused.upc": "999111", "fused.description": "Mug"},
        )))
        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            extra_messages=[
                {"sender_type": "human", "content": "Use 999111."},
            ],
        )
        await dispatch_on_human_message(thread_id, "t1")

        item = await _fetch_item(
            seeded["factory"], seeded["order_id"], seeded["item_no"],
        )
        assert item.data["fused"] == {"upc": "999111", "description": "Mug"}


# ── Auto-resolve + auto-advance ─────────────────────────────────────────────


class TestDispatcherResolved:
    @pytest.mark.asyncio
    async def test_resolved_closes_thread_and_fires_auto_advance(
        self, seeded, router, registry, auto_advance_calls,
    ):
        register_chat_handler(_FakeHandler(ChatReply(
            text="All set — re-running the pipeline.",
            patches={"country_of_origin": "CN"},
            resolved=True,
        )))
        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            extra_messages=[
                {"sender_type": "human", "content": "Use CN."},
            ],
        )
        reply = await dispatch_on_human_message(thread_id, "t1")
        assert reply is not None and reply.resolved is True

        # Thread is now RESOLVED
        thread = await _fetch_thread(seeded["factory"], thread_id)
        assert thread is not None
        assert thread.status == "RESOLVED"
        assert thread.resolved_at is not None

        # Auto-advance hook called once with the right tenant/order
        assert auto_advance_calls == [("t1", seeded["order_id"])]

    @pytest.mark.asyncio
    async def test_unresolved_does_not_fire_auto_advance(
        self, seeded, router, registry, auto_advance_calls,
    ):
        register_chat_handler(_FakeHandler(ChatReply(
            text="Need more info.",
            resolved=False,
        )))
        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            extra_messages=[
                {"sender_type": "human", "content": "Why?"},
            ],
        )
        await dispatch_on_human_message(thread_id, "t1")

        thread = await _fetch_thread(seeded["factory"], thread_id)
        assert thread.status == "IN_PROGRESS"
        assert auto_advance_calls == []


# ── Safety rails ────────────────────────────────────────────────────────────


class TestDispatcherSafetyRails:
    @pytest.mark.asyncio
    async def test_terminal_thread_is_a_noop(
        self, seeded, router, registry,
    ):
        handler = _FakeHandler(ChatReply(text="should not fire"))
        register_chat_handler(handler)
        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
        )
        # Flip to RESOLVED directly
        async with seeded["factory"]() as s:
            thread = (await s.execute(
                select(HiTLThreadModel).where(HiTLThreadModel.id == thread_id)
            )).scalar_one()
            thread.status = "RESOLVED"
            await s.commit()

        reply = await dispatch_on_human_message(thread_id, "t1")
        assert reply is None
        assert handler.calls == []  # handler never invoked

    @pytest.mark.asyncio
    async def test_missing_handler_posts_boilerplate(
        self, seeded, router, registry,
    ):
        # No handler registered for agent_id="fake"
        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            extra_messages=[
                {"sender_type": "human", "content": "hi"},
            ],
        )
        reply = await dispatch_on_human_message(thread_id, "t1")
        assert reply is None  # no handler → no ChatReply

        msgs = await _fetch_messages(seeded["factory"], thread_id)
        system_msg = next(m for m in msgs if m.sender_type == "system")
        assert "fake" in system_msg.content
        assert system_msg.context.get("action") == "no_handler"

    @pytest.mark.asyncio
    async def test_turn_cap_posts_system_message(
        self, seeded, router, registry,
    ):
        handler = _FakeHandler(ChatReply(text="should not fire"))
        register_chat_handler(handler)
        # Seed MAX_AGENT_TURNS agent messages so the next turn exceeds the cap.
        extra = []
        for i in range(MAX_AGENT_TURNS):
            extra.append({"sender_type": "agent", "content": f"turn {i}"})
        extra.append({"sender_type": "human", "content": "still stuck?"})
        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            extra_messages=extra,
        )
        reply = await dispatch_on_human_message(thread_id, "t1")
        assert reply is None
        assert handler.calls == []  # handler never invoked — cap enforced

        msgs = await _fetch_messages(seeded["factory"], thread_id)
        cap_msg = next(m for m in msgs if m.sender_type == "system")
        assert cap_msg.context.get("action") == "chat_turn_cap"

    @pytest.mark.asyncio
    async def test_cross_tenant_dispatch_is_noop(
        self, seeded, router, registry,
    ):
        handler = _FakeHandler(ChatReply(text="nope"))
        register_chat_handler(handler)
        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            extra_messages=[
                {"sender_type": "human", "content": "hi"},
            ],
        )
        # Wrong tenant — dispatcher must not produce a reply.
        reply = await dispatch_on_human_message(thread_id, "wrong-tenant")
        assert reply is None
        assert handler.calls == []

    @pytest.mark.asyncio
    async def test_publishes_typing_start_and_stop(
        self, seeded, router, registry,
    ):
        """Dispatcher publishes ``typing/start`` before the LLM call and
        ``typing/stop`` after. The frontend uses these to flip the
        "agent is thinking…" bubble.
        """
        register_chat_handler(_FakeHandler(ChatReply(text="ok")))
        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            extra_messages=[
                {"sender_type": "human", "content": "hi"},
            ],
        )
        sub = router.subscribe(thread_id)
        await dispatch_on_human_message(thread_id, "t1")

        # Drain all envelopes produced during dispatch so we can assert
        # the typing pair is present.
        seen: List[Dict[str, Any]] = []
        import asyncio as _asyncio
        try:
            while True:
                env = await _asyncio.wait_for(sub.__anext__(), timeout=0.2)
                seen.append(env)
        except (_asyncio.TimeoutError, StopAsyncIteration):
            pass
        await sub.unsubscribe()

        typing_events = [e for e in seen if e["type"] == "typing"]
        # At minimum: one start + one stop, both role=agent.
        states = [e["payload"].get("state") for e in typing_events]
        roles = {e["payload"].get("role") for e in typing_events}
        assert "start" in states
        assert "stop" in states
        assert roles == {"agent"}

    @pytest.mark.asyncio
    async def test_agent_reply_does_not_retrigger_dispatch(
        self, seeded, router, registry,
    ):
        """The dispatcher writes an agent message through the resolver;
        the resolver only schedules re-dispatch on sender_type=human, so
        a single dispatch call must produce exactly one handler invocation
        — no runaway loop.
        """
        handler = _FakeHandler(ChatReply(text="Done."))
        register_chat_handler(handler)
        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            extra_messages=[
                {"sender_type": "human", "content": "hi"},
            ],
        )
        await dispatch_on_human_message(thread_id, "t1")
        # Handler saw exactly one turn
        assert len(handler.calls) == 1
        # And the thread has exactly one NEW agent message (beyond the opener)
        msgs = await _fetch_messages(seeded["factory"], thread_id)
        agent_msgs = [m for m in msgs if m.sender_type == "agent"]
        assert len(agent_msgs) == 2  # opener + dispatcher reply


# ── Tool-use loop (DieCut HiTL access plan) ────────────────────────────────


class _ScriptedHandler(AgentChatHandler):
    """Handler that replays a pre-recorded sequence of ChatReplys.

    Each call to :meth:`respond` pops the next reply off the queue and
    records the incoming :class:`ChatContext`. Used to verify the
    dispatcher's tool-use loop re-invokes the handler with augmented
    message history and eventually persists only the final visible text.
    """

    agent_id = "scripted"
    patch_allowlist = ("*",)

    def __init__(self, replies, *, agent_id: str = "scripted") -> None:
        super().__init__()
        self.agent_id = agent_id
        self._replies = list(replies)
        self.calls: List[ChatContext] = []

    async def respond(self, ctx: ChatContext) -> ChatReply:  # type: ignore[override]
        self.calls.append(ctx)
        if not self._replies:
            return ChatReply(text="(exhausted)")
        return self._replies.pop(0)


class TestDispatcherToolLoop:
    @pytest.mark.asyncio
    async def test_tool_call_executes_and_final_reply_persists(
        self, seeded, router, registry,
    ):
        """Turn 1 emits a non-substantive marker AND a ``tools`` array;
        turn 2 emits the final prose. The dispatcher must run the tool,
        append its result as a system message, and persist the final
        prose as the agent message.

        The turn-1 placeholder text here is deliberately short so
        ``_is_substantive`` rejects it — if the LLM had said something
        meaningful alongside its tool call we'd persist that separately
        (see :class:`TestDispatcherInterimStatus`)."""
        # Seed one ImporterDocument so list_importer_documents has
        # something to return.
        factory = seeded["factory"]
        # Pull the importer_id from the seeded order so the tool sees it.
        async with factory() as s:
            row = (await s.execute(
                select(Order).where(Order.id == seeded["order_id"])
            )).scalar_one_or_none()
            importer_id = row.importer_id
            s.add(ImporterDocument(
                id="idoc-test-001",
                tenant_id="t1",
                importer_id=importer_id,
                doc_type="protocol",
                filename="carton-marking.pdf",
                s3_key="unused/dev.pdf",
                content_hash="sha256:deadbeef",
                size_bytes=1024,
                version=1,
            ))
            await s.commit()

        handler = _ScriptedHandler([
            # Turn 1 — non-substantive marker (< 8 chars so the interim
            # persister skips it). Exercises the "pure tool call, no
            # user-facing prose" path.
            ChatReply(
                text="...",
                tool_calls=[{"name": "list_importer_documents", "args": {}}],
            ),
            # Turn 2 — final visible answer after the tool result arrives
            ChatReply(
                text="I can see idoc-test-001 (carton-marking.pdf). "
                     "Here's the summary you asked for.",
            ),
        ])
        register_chat_handler(handler)

        thread_id = await _open_thread(
            factory,
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            agent_id="scripted",
            extra_messages=[{"sender_type": "human", "content": "what docs do we have?"}],
        )

        await dispatch_on_human_message(thread_id, "t1")

        # Handler called exactly twice; turn 2 received the synthetic
        # [tool_result:...] system message from turn 1.
        assert len(handler.calls) == 2
        turn2_messages = handler.calls[1].messages
        tool_msgs = [m for m in turn2_messages if m.role == "system" and "[tool_result:list_importer_documents]" in m.content]
        assert len(tool_msgs) == 1
        assert "idoc-test-001" in tool_msgs[0].content

        # Only the final reply persisted — the non-substantive "..."
        # placeholder must NOT be stored on the thread.
        msgs = await _fetch_messages(factory, thread_id)
        agent_msgs = [m for m in msgs if m.sender_type == "agent"]
        # Opener + one dispatcher reply == 2; no interim (turn-1 text
        # was too short to qualify as substantive).
        assert len(agent_msgs) == 2
        assert "idoc-test-001" in agent_msgs[-1].content
        assert agent_msgs[-1].content.count("...") == 0

    @pytest.mark.asyncio
    async def test_tool_loop_caps_at_three_rounds(
        self, seeded, router, registry,
    ):
        """A handler that asks for a tool every turn must eventually be
        terminated by the loop cap so dispatch can't hang."""
        handler = _ScriptedHandler([
            # Rounds 1..3 keep asking for tools.
            ChatReply(text="r1", tool_calls=[{"name": "list_importer_documents", "args": {}}]),
            ChatReply(text="r2", tool_calls=[{"name": "list_importer_documents", "args": {}}]),
            ChatReply(text="r3", tool_calls=[{"name": "list_importer_documents", "args": {}}]),
            # Round 4 (the post-cap fallback) emits plain text.
            ChatReply(text="final answer after cap"),
        ])
        register_chat_handler(handler)

        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            agent_id="scripted",
            extra_messages=[{"sender_type": "human", "content": "go"}],
        )

        await dispatch_on_human_message(thread_id, "t1")

        # The dispatcher stops looping after _MAX_TOOL_ROUNDS and persists
        # the final answer, never the intermediate "r1"/"r2"/"r3" text.
        msgs = await _fetch_messages(seeded["factory"], thread_id)
        agent_msgs = [m for m in msgs if m.sender_type == "agent"]
        assert agent_msgs[-1].content == "final answer after cap"
        for mid_text in ("r1", "r2", "r3"):
            assert not any(m.content == mid_text for m in agent_msgs), (
                f"intermediate reply {mid_text!r} leaked to thread"
            )


class TestDispatcherStaticContext:
    @pytest.mark.asyncio
    async def test_context_includes_profile_rules_docs_and_siblings(
        self, seeded, router, registry,
    ):
        """`_build_chat_context` prefetches bounded tenant/order data
        onto the ChatContext so simple questions need zero tool calls."""
        factory = seeded["factory"]
        async with factory() as s:
            row = (await s.execute(
                select(Order).where(Order.id == seeded["order_id"])
            )).scalar_one_or_none()
            importer_id = row.importer_id

            s.add(ImporterProfileModel(
                id=str(uuid4()),
                importer_id=importer_id,
                tenant_id="t1",
                version=1,
                brand_treatment={"company_name": "Acme"},
                panel_layouts={"front": ["logo"]},
                handling_symbol_rules={"fragile": True},
            ))
            s.add(ComplianceRule(
                id=str(uuid4()),
                tenant_id="t1",
                rule_code="R_TEST",
                title="test rule",
                region="US",
                placement="both",
                logic={"always_pass": True},
                is_active=True,
            ))
            s.add(WarningLabel(
                id=str(uuid4()),
                tenant_id="t1",
                code="WL_TEST",
                title="test",
                text_en="Do not eat.",
                region="US",
                placement="both",
                is_active=True,
            ))
            s.add(ImporterDocument(
                id="idoc-ctx-001",
                tenant_id="t1",
                importer_id=importer_id,
                doc_type="protocol",
                filename="proto.pdf",
                s3_key="unused/dev.pdf",
                content_hash="sha256:x",
                size_bytes=10,
                version=1,
            ))
            # Sibling item on the same order.
            s.add(OrderItemModel(
                id=str(uuid4()),
                order_id=seeded["order_id"],
                tenant_id="t1",
                item_no="SIB",
                state="FUSED",
                data={"upc": "999"},
            ))
            await s.commit()

        captured: List[ChatContext] = []

        class _Capturer(AgentChatHandler):
            agent_id = "scripted"
            patch_allowlist = ("*",)

            async def respond(self, ctx):  # type: ignore[override]
                captured.append(ctx)
                return ChatReply(text="ok")

        register_chat_handler(_Capturer())

        thread_id = await _open_thread(
            factory,
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            agent_id="scripted",
            extra_messages=[{"sender_type": "human", "content": "hi"}],
        )
        await dispatch_on_human_message(thread_id, "t1")

        assert captured, "handler never invoked"
        ctx = captured[0]
        assert ctx.importer_profile is not None
        assert ctx.importer_profile.get("brand_treatment") == {"company_name": "Acme"}
        assert any(r.get("rule_code") == "R_TEST" for r in ctx.rules_summary)
        assert any(w.get("code") == "WL_TEST" for w in ctx.warnings_summary)
        assert any(d.get("id") == "idoc-ctx-001" for d in ctx.documents_summary)
        sibling_nos = [s.get("item_no") for s in ctx.sibling_items]
        assert "SIB" in sibling_nos
        # The current item must NOT appear in siblings.
        assert seeded["item_no"] not in sibling_nos


# ── Interim status + vacuous-reply rewrite (bot-goes-to-sleep fix) ────────


class TestDispatcherInterimStatus:
    @pytest.mark.asyncio
    async def test_prose_with_tool_call_persists_as_intermediate_message(
        self, seeded, router, registry,
    ):
        """When turn 1 emits BOTH visible prose and a tools array, the
        prose is persisted as an agent message with
        ``context={"intermediate": True, ...}`` so the operator sees
        progress instead of silence while the tool runs + turn 2 cooks."""
        handler = _ScriptedHandler([
            ChatReply(
                text="Sure — let me pull the compliance rules for this tenant first.",
                tool_calls=[{"name": "list_compliance_rules", "args": {}}],
            ),
            ChatReply(
                text="Found 0 rules. Looks like the tenant's rule table is empty.",
            ),
        ])
        register_chat_handler(handler)

        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            agent_id="scripted",
            extra_messages=[{"sender_type": "human", "content": "list rules please"}],
        )

        await dispatch_on_human_message(thread_id, "t1")

        msgs = await _fetch_messages(seeded["factory"], thread_id)
        agent_msgs = [m for m in msgs if m.sender_type == "agent"]
        # Opener + interim + final = 3.
        assert len(agent_msgs) == 3
        interim = agent_msgs[1]
        assert "compliance rules" in interim.content.lower()
        assert interim.context and interim.context.get("intermediate") is True
        assert interim.context.get("tools_pending") == ["list_compliance_rules"]
        # Final message is still the substantive answer.
        assert "Found 0 rules" in agent_msgs[-1].content
        # And the final message is NOT flagged intermediate.
        assert not (agent_msgs[-1].context or {}).get("intermediate")

    @pytest.mark.asyncio
    async def test_vacuous_final_reply_rewritten_to_tool_summary(
        self, seeded, router, registry,
    ):
        """After a tool runs, if the LLM's final turn is an empty polite
        ack, the dispatcher swaps in a bullet-list summary of what was
        fetched so the user doesn't get stuck staring at "Got it."."""
        factory = seeded["factory"]
        async with factory() as s:
            s.add(ComplianceRule(
                id=str(uuid4()),
                tenant_id="t1",
                rule_code="R_SUMMARY_TEST",
                title="summary test",
                region="US",
                placement="both",
                logic={"always_pass": True},
                is_active=True,
            ))
            await s.commit()

        handler = _ScriptedHandler([
            ChatReply(
                text="",
                tool_calls=[{"name": "list_compliance_rules", "args": {}}],
            ),
            ChatReply(text="Got it."),
        ])
        register_chat_handler(handler)

        thread_id = await _open_thread(
            factory,
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            agent_id="scripted",
            extra_messages=[{"sender_type": "human", "content": "run the tool"}],
        )
        await dispatch_on_human_message(thread_id, "t1")

        msgs = await _fetch_messages(factory, thread_id)
        final_agent = [m for m in msgs if m.sender_type == "agent"][-1]
        # The "Got it." vacuous reply was rewritten.
        assert final_agent.content != "Got it."
        assert "quick summary" in final_agent.content.lower()
        assert "list_compliance_rules" in final_agent.content
        assert "R_SUMMARY_TEST" in final_agent.content  # cited from results

    @pytest.mark.asyncio
    async def test_substantive_final_reply_not_rewritten(
        self, seeded, router, registry,
    ):
        """If the LLM actually said something concrete, leave it alone —
        the rewrite only rescues vacuous replies."""
        handler = _ScriptedHandler([
            ChatReply(
                text="",
                tool_calls=[{"name": "list_compliance_rules", "args": {}}],
            ),
            ChatReply(
                text="I found one rule: R_KEEP_ME. It's always-pass for US "
                     "and applies to all items — no further action needed.",
            ),
        ])
        register_chat_handler(handler)

        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            agent_id="scripted",
            extra_messages=[{"sender_type": "human", "content": "run it"}],
        )
        await dispatch_on_human_message(thread_id, "t1")

        msgs = await _fetch_messages(seeded["factory"], thread_id)
        final_agent = [m for m in msgs if m.sender_type == "agent"][-1]
        assert "R_KEEP_ME" in final_agent.content
        # Not wrapped in the summary template.
        assert "quick summary of what I pulled" not in final_agent.content.lower()


# ── Turn-cap semantics (intermediate messages don't count) ─────────────────


class TestDispatcherTurnCapCounting:
    @pytest.mark.asyncio
    async def test_intermediate_agent_messages_do_not_count_toward_cap(
        self, seeded, router, registry,
    ):
        """Seed MAX_AGENT_TURNS intermediate agent messages and one real
        final agent reply — the cap should NOT trip. Interim status
        messages from tool rounds (``context.intermediate=True``) are
        UX feedback, not independent agent turns."""
        handler = _FakeHandler(ChatReply(text="Still responsive."))
        register_chat_handler(handler)

        extra = []
        # Many interim-flagged agent messages — should be ignored by the
        # turn counter.
        for i in range(MAX_AGENT_TURNS + 5):
            extra.append({
                "sender_type": "agent",
                "content": f"interim {i}",
                "context": {"intermediate": True, "round": 1},
            })
        # Exactly one *real* agent reply.
        extra.append({
            "sender_type": "agent",
            "content": "previous real reply",
        })
        extra.append({"sender_type": "human", "content": "keep going"})

        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            extra_messages=extra,
        )
        reply = await dispatch_on_human_message(thread_id, "t1")
        assert reply is not None
        # Handler invoked (cap NOT tripped).
        assert handler.calls, "handler should have been called"

    @pytest.mark.asyncio
    async def test_substantive_agent_messages_still_count(
        self, seeded, router, registry,
    ):
        """Sanity — non-intermediate replies still count, so the runaway
        protection isn't defeated."""
        handler = _FakeHandler(ChatReply(text="should not fire"))
        register_chat_handler(handler)
        extra = [
            {"sender_type": "agent", "content": f"real {i}"}
            for i in range(MAX_AGENT_TURNS)
        ]
        extra.append({"sender_type": "human", "content": "still stuck?"})
        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            extra_messages=extra,
        )
        reply = await dispatch_on_human_message(thread_id, "t1")
        assert reply is None
        assert handler.calls == []


# ── System-message broadcast carries created_at (Invalid Date fix) ─────────


class TestSystemMessageBroadcast:
    @pytest.mark.asyncio
    async def test_cap_system_message_ws_envelope_has_created_at(
        self, seeded, router, registry,
    ):
        """The cap / no-handler system message used to broadcast with
        ``created_at=null`` — the frontend rendered it as "Invalid Date".
        After the fix we refresh the row post-commit and include the
        ISO timestamp on the envelope."""
        extra = [
            {"sender_type": "agent", "content": f"turn {i}"}
            for i in range(MAX_AGENT_TURNS)
        ]
        extra.append({"sender_type": "human", "content": "please help"})
        thread_id = await _open_thread(
            seeded["factory"],
            order_id=seeded["order_id"],
            item_no=seeded["item_no"],
            extra_messages=extra,
        )

        captured: List[Dict[str, Any]] = []
        import asyncio as _aio

        sub = router.subscribe(thread_id)

        async def _drain() -> None:
            try:
                async for env in sub:
                    captured.append(env)
            except _aio.CancelledError:
                pass

        drain_task = _aio.create_task(_drain())
        try:
            await dispatch_on_human_message(thread_id, "t1")
            # Let the publish callback flush through the queue.
            await _aio.sleep(0.1)
        finally:
            await sub.unsubscribe()
            try:
                await _aio.wait_for(drain_task, timeout=1.0)
            except _aio.TimeoutError:
                drain_task.cancel()

        agent_envs = [
            e for e in captured
            if (e.get("type") if isinstance(e, dict) else None) == "agent_message"
        ]
        assert agent_envs, f"no agent_message broadcast captured: {captured!r}"
        payload = agent_envs[-1].get("payload") or {}
        assert payload.get("sender_type") == "system"
        assert payload.get("created_at"), (
            f"created_at missing from system broadcast payload: {payload!r}"
        )
