"""Tests for labelforge.services.hitl.router (Sprint-14, TASK-030)."""
from __future__ import annotations

import asyncio

import pytest

from labelforge.services.hitl.router import (
    EventType,
    InMemoryMessageRouter,
    make_envelope,
)


@pytest.mark.asyncio
async def test_envelope_shape_includes_all_fields():
    env = make_envelope(EventType.AGENT_MESSAGE, "t1", {"content": "hi"})
    assert set(env) == {"type", "thread_id", "payload", "ts"}
    assert env["type"] == "agent_message"
    assert env["thread_id"] == "t1"
    assert env["payload"] == {"content": "hi"}
    assert env["ts"].endswith("+00:00") or "Z" in env["ts"]


class TestInMemoryRouterSinglePair:
    @pytest.mark.asyncio
    async def test_publish_reaches_subscriber(self):
        r = InMemoryMessageRouter()
        sub = r.subscribe("t1")
        await r.publish("t1", make_envelope(EventType.AGENT_MESSAGE, "t1", {"x": 1}))
        env = await asyncio.wait_for(sub.__anext__(), timeout=0.5)
        assert env["type"] == "agent_message"
        assert env["payload"]["x"] == 1
        await sub.unsubscribe()

    @pytest.mark.asyncio
    async def test_isolation_between_threads(self):
        r = InMemoryMessageRouter()
        a = r.subscribe("t1")
        b = r.subscribe("t2")
        await r.publish("t1", make_envelope(EventType.AGENT_MESSAGE, "t1", {"x": 1}))

        env = await asyncio.wait_for(a.__anext__(), timeout=0.5)
        assert env["thread_id"] == "t1"

        # t2 subscriber should see nothing — timeout.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(b.__anext__(), timeout=0.15)

        await a.unsubscribe()
        await b.unsubscribe()

    @pytest.mark.asyncio
    async def test_multiple_subscribers_each_receive(self):
        r = InMemoryMessageRouter()
        s1 = r.subscribe("t1")
        s2 = r.subscribe("t1")
        assert r.subscriber_count("t1") == 2

        await r.publish("t1", make_envelope(EventType.HUMAN_MESSAGE, "t1", {}))
        e1 = await asyncio.wait_for(s1.__anext__(), timeout=0.5)
        e2 = await asyncio.wait_for(s2.__anext__(), timeout=0.5)
        assert e1["type"] == e2["type"] == "human_message"
        await s1.unsubscribe()
        await s2.unsubscribe()

    @pytest.mark.asyncio
    async def test_unsubscribe_terminates_iterator(self):
        r = InMemoryMessageRouter()
        sub = r.subscribe("t1")
        await sub.unsubscribe()
        # Iterator should raise StopAsyncIteration (loop body never runs).
        with pytest.raises(StopAsyncIteration):
            await sub.__anext__()
        assert r.subscriber_count("t1") == 0

    @pytest.mark.asyncio
    async def test_publish_to_empty_channel_is_noop(self):
        r = InMemoryMessageRouter()
        # Should not raise, even with no subscribers.
        await r.publish("nobody-here", make_envelope("ping", "nobody-here", {}))

    @pytest.mark.asyncio
    async def test_aclose_closes_all_subscriptions(self):
        r = InMemoryMessageRouter()
        a = r.subscribe("t1")
        b = r.subscribe("t2")
        await r.aclose()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(a.__anext__(), timeout=0.5)
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(b.__anext__(), timeout=0.5)

    @pytest.mark.asyncio
    async def test_event_ordering_preserved(self):
        r = InMemoryMessageRouter()
        sub = r.subscribe("t1")
        for i in range(5):
            await r.publish("t1", make_envelope("agent_message", "t1", {"i": i}))
        seen = []
        for _ in range(5):
            env = await asyncio.wait_for(sub.__anext__(), timeout=0.5)
            seen.append(env["payload"]["i"])
        assert seen == [0, 1, 2, 3, 4]
        await sub.unsubscribe()

    @pytest.mark.asyncio
    async def test_all_event_types_roundtrip(self):
        """Each of the 7 router event types can be published + received."""
        r = InMemoryMessageRouter()
        sub = r.subscribe("t1")
        types = [
            EventType.AGENT_MESSAGE,
            EventType.HUMAN_MESSAGE,
            EventType.STATUS_UPDATE,
            EventType.ESCALATION,
            EventType.TYPING,
            EventType.OPTION_SELECTED,
            EventType.THREAD_RESOLVED,
        ]
        for t in types:
            await r.publish("t1", make_envelope(t, "t1", {}))
        seen_types = [
            (await asyncio.wait_for(sub.__anext__(), timeout=0.5))["type"]
            for _ in types
        ]
        assert seen_types == types
        await sub.unsubscribe()
