"""Tests for labelforge.services.notifications.dispatcher (Sprint-15, TASK-038)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Awaitable, Callable

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from labelforge.db.base import Base
from labelforge.db.models import AuditLog, Notification as NotificationModel, Tenant
from labelforge.services.notifications import (
    Channel,
    EmailTransport,
    InAppTransport,
    InMemoryPreferenceStore,
    NotificationDispatcher,
    NotificationSpec,
    PagerDutyTransport,
    SlackTransport,
    TransientFailure,
    Transport,
    get_dispatcher,
    set_dispatcher,
)


# ── Fakes ────────────────────────────────────────────────────────────────────


class FakeTransport:
    """Counts calls, optionally raising on the first N attempts."""

    def __init__(self, channel: Channel, *, transient_fails: int = 0, permanent: bool = False) -> None:
        self.channel = channel
        self.calls: list[NotificationSpec] = []
        self._transient_fails = transient_fails
        self._permanent = permanent

    async def send(self, spec: NotificationSpec) -> dict[str, Any]:
        self.calls.append(spec)
        if self._permanent:
            raise RuntimeError("permanent failure")
        if self._transient_fails > 0:
            self._transient_fails -= 1
            raise TransientFailure("try again")
        return {"channel": self.channel.value, "attempt_count": len(self.calls)}


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def session_factory():
    """In-memory SQLite session factory with a preseeded tenant."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add(Tenant(id="t1", name="T1", slug="t1"))
        await s.commit()
    yield factory
    await engine.dispose()


@pytest.fixture
def no_sleep():
    """Replace asyncio.sleep with an immediate no-op."""
    calls: list[float] = []

    async def fake(seconds: float) -> None:
        calls.append(seconds)

    fake.calls = calls  # type: ignore[attr-defined]
    return fake


@pytest.fixture(autouse=True)
def _reset_dispatcher():
    set_dispatcher(None)
    yield
    set_dispatcher(None)


# ── Basic routing ────────────────────────────────────────────────────────────


class TestRouting:
    @pytest.mark.asyncio
    async def test_each_channel_dispatches_once(self, no_sleep):
        email = FakeTransport(Channel.EMAIL)
        slack = FakeTransport(Channel.SLACK)
        pager = FakeTransport(Channel.PAGERDUTY)

        dispatcher = NotificationDispatcher(
            transports=[email, slack, pager],
            sleep=no_sleep,
        )
        spec = NotificationSpec(
            tenant_id="t1",
            event_type="cost_breaker.triggered",
            title="Cost breaker fired",
            body="Daily limit exceeded.",
            channels=[Channel.EMAIL, Channel.SLACK, Channel.PAGERDUTY],
            level="critical",
            user_email="ops@example.com",
        )

        result = await dispatcher.dispatch(spec)

        assert result[Channel.EMAIL]["status"] == "sent"
        assert result[Channel.SLACK]["status"] == "sent"
        assert result[Channel.PAGERDUTY]["status"] == "sent"
        assert len(email.calls) == 1
        assert len(slack.calls) == 1
        assert len(pager.calls) == 1

    @pytest.mark.asyncio
    async def test_unregistered_channel_is_skipped(self, no_sleep):
        email = FakeTransport(Channel.EMAIL)
        dispatcher = NotificationDispatcher(transports=[email], sleep=no_sleep)
        spec = NotificationSpec(
            tenant_id="t1",
            event_type="x",
            title="t",
            body="b",
            channels=[Channel.SLACK],
        )
        result = await dispatcher.dispatch(spec)
        assert result[Channel.SLACK]["status"] == "skipped"
        assert "no transport registered" in result[Channel.SLACK]["error"]
        assert email.calls == []

    @pytest.mark.asyncio
    async def test_register_adds_transport(self, no_sleep):
        dispatcher = NotificationDispatcher(sleep=no_sleep)
        assert dispatcher.channels() == []
        dispatcher.register(FakeTransport(Channel.IN_APP))
        assert Channel.IN_APP in dispatcher.channels()


# ── Preferences ──────────────────────────────────────────────────────────────


class TestPreferences:
    @pytest.mark.asyncio
    async def test_mute_channel_blocks_dispatch(self, no_sleep):
        prefs = InMemoryPreferenceStore()
        prefs.mute_channel("t1", Channel.SLACK)
        slack = FakeTransport(Channel.SLACK)
        dispatcher = NotificationDispatcher(
            transports=[slack], preferences=prefs, sleep=no_sleep
        )
        spec = NotificationSpec(
            tenant_id="t1", event_type="x", title="t", body="b",
            channels=[Channel.SLACK],
        )
        result = await dispatcher.dispatch(spec)
        assert result[Channel.SLACK]["status"] == "muted"
        assert slack.calls == []

    @pytest.mark.asyncio
    async def test_event_specific_override_wins(self, no_sleep):
        prefs = InMemoryPreferenceStore()
        # Channel-level mute but explicit override re-enables this event.
        prefs.mute_channel("t1", Channel.EMAIL)
        prefs.set("t1", Channel.EMAIL, "cost_breaker.triggered", enabled=True)
        email = FakeTransport(Channel.EMAIL)
        d = NotificationDispatcher(transports=[email], preferences=prefs, sleep=no_sleep)

        # Unmuted event sends…
        fire = NotificationSpec(
            tenant_id="t1", event_type="cost_breaker.triggered",
            title="t", body="b", channels=[Channel.EMAIL], user_email="a@b",
        )
        await d.dispatch(fire)
        # …but another event stays muted.
        other = NotificationSpec(
            tenant_id="t1", event_type="order.updated",
            title="t", body="b", channels=[Channel.EMAIL], user_email="a@b",
        )
        await d.dispatch(other)
        assert len(email.calls) == 1
        assert email.calls[0].event_type == "cost_breaker.triggered"

    @pytest.mark.asyncio
    async def test_per_tenant_isolation(self, no_sleep):
        prefs = InMemoryPreferenceStore()
        prefs.mute_channel("t1", Channel.SLACK)
        slack = FakeTransport(Channel.SLACK)
        d = NotificationDispatcher(transports=[slack], preferences=prefs, sleep=no_sleep)

        muted = NotificationSpec(tenant_id="t1", event_type="x", title="t", body="b", channels=[Channel.SLACK])
        active = NotificationSpec(tenant_id="t2", event_type="x", title="t", body="b", channels=[Channel.SLACK])
        r1 = await d.dispatch(muted)
        r2 = await d.dispatch(active)
        assert r1[Channel.SLACK]["status"] == "muted"
        assert r2[Channel.SLACK]["status"] == "sent"
        assert len(slack.calls) == 1


# ── Retries ──────────────────────────────────────────────────────────────────


class TestRetries:
    @pytest.mark.asyncio
    async def test_retries_transient_failure(self, no_sleep):
        t = FakeTransport(Channel.SLACK, transient_fails=2)
        d = NotificationDispatcher(
            transports=[t], max_retries=3, retry_base_seconds=0.1, sleep=no_sleep
        )
        spec = NotificationSpec(
            tenant_id="t1", event_type="x", title="t", body="b",
            channels=[Channel.SLACK],
        )
        result = await d.dispatch(spec)
        assert result[Channel.SLACK]["status"] == "sent"
        assert result[Channel.SLACK]["attempts"] == 3
        # Two sleeps (before attempts 2 and 3), exponential backoff.
        assert no_sleep.calls == [0.1, 0.2]

    @pytest.mark.asyncio
    async def test_exhausts_retries_and_reports_failed(self, no_sleep):
        t = FakeTransport(Channel.SLACK, transient_fails=10)
        d = NotificationDispatcher(
            transports=[t], max_retries=2, retry_base_seconds=0.0, sleep=no_sleep
        )
        spec = NotificationSpec(
            tenant_id="t1", event_type="x", title="t", body="b",
            channels=[Channel.SLACK],
        )
        result = await d.dispatch(spec)
        assert result[Channel.SLACK]["status"] == "failed"
        assert result[Channel.SLACK]["attempts"] == 3  # 1 + 2 retries
        assert "try again" in result[Channel.SLACK]["error"]

    @pytest.mark.asyncio
    async def test_permanent_failure_is_not_retried(self, no_sleep):
        t = FakeTransport(Channel.SLACK, permanent=True)
        d = NotificationDispatcher(
            transports=[t], max_retries=5, retry_base_seconds=0.0, sleep=no_sleep
        )
        spec = NotificationSpec(
            tenant_id="t1", event_type="x", title="t", body="b",
            channels=[Channel.SLACK],
        )
        result = await d.dispatch(spec)
        assert result[Channel.SLACK]["status"] == "failed"
        assert result[Channel.SLACK]["attempts"] == 1
        assert "permanent failure" in result[Channel.SLACK]["error"]
        assert no_sleep.calls == []  # no sleeps

    @pytest.mark.asyncio
    async def test_zero_retries_disabled(self, no_sleep):
        t = FakeTransport(Channel.SLACK, transient_fails=1)
        d = NotificationDispatcher(
            transports=[t], max_retries=0, sleep=no_sleep
        )
        result = await d.dispatch(
            NotificationSpec(
                tenant_id="t1", event_type="x", title="t", body="b",
                channels=[Channel.SLACK],
            )
        )
        assert result[Channel.SLACK]["status"] == "failed"


# ── Audit logging ────────────────────────────────────────────────────────────


class TestAuditLogging:
    @pytest.mark.asyncio
    async def test_success_writes_audit_row(self, session_factory, no_sleep):
        t = FakeTransport(Channel.EMAIL)
        d = NotificationDispatcher(
            transports=[t],
            audit_session_factory=session_factory,
            sleep=no_sleep,
        )
        spec = NotificationSpec(
            tenant_id="t1", event_type="order.completed",
            title="Done", body="All good", level="info",
            channels=[Channel.EMAIL], user_email="a@b",
        )
        await d.dispatch(spec)

        async with session_factory() as s:
            rows = (await s.execute(select(AuditLog))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.tenant_id == "t1"
        assert row.action == "notification.sent"
        assert row.resource_type == "notification"
        assert row.details["channel"] == "email"
        assert row.details["event_type"] == "order.completed"
        assert row.actor == "notification_dispatcher"
        assert row.actor_type == "system"

    @pytest.mark.asyncio
    async def test_failure_writes_audit_row(self, session_factory, no_sleep):
        t = FakeTransport(Channel.SLACK, transient_fails=99)
        d = NotificationDispatcher(
            transports=[t],
            audit_session_factory=session_factory,
            max_retries=1,
            retry_base_seconds=0.0,
            sleep=no_sleep,
        )
        await d.dispatch(
            NotificationSpec(
                tenant_id="t1", event_type="x",
                title="t", body="b",
                channels=[Channel.SLACK],
            )
        )
        async with session_factory() as s:
            rows = (await s.execute(select(AuditLog))).scalars().all()
        assert rows[0].action == "notification.failed"
        assert rows[0].details["attempts"] == 2
        assert rows[0].details["error"]

    @pytest.mark.asyncio
    async def test_mute_also_audited(self, session_factory, no_sleep):
        prefs = InMemoryPreferenceStore()
        prefs.mute_channel("t1", Channel.SLACK)
        t = FakeTransport(Channel.SLACK)
        d = NotificationDispatcher(
            transports=[t], preferences=prefs,
            audit_session_factory=session_factory,
            sleep=no_sleep,
        )
        await d.dispatch(
            NotificationSpec(
                tenant_id="t1", event_type="x", title="t", body="b",
                channels=[Channel.SLACK],
            )
        )
        async with session_factory() as s:
            rows = (await s.execute(select(AuditLog))).scalars().all()
        assert len(rows) == 1
        assert rows[0].action == "notification.muted"


# ── Swappable transports ─────────────────────────────────────────────────────


class TestTransports:
    @pytest.mark.asyncio
    async def test_email_transport_uses_injected_sender(self):
        captured: list[EmailMessage] = []

        def sender(msg: EmailMessage) -> None:
            captured.append(msg)

        t = EmailTransport(from_addr="bot@lf.test", sender=sender)
        spec = NotificationSpec(
            tenant_id="t1", event_type="x", title="Hello",
            body="World", channels=[Channel.EMAIL],
            user_email="u@example.com",
        )
        await t.send(spec)
        assert captured
        msg = captured[0]
        assert msg["To"] == "u@example.com"
        assert msg["From"] == "bot@lf.test"
        assert "Hello" in msg["Subject"]
        assert "World" in msg.get_content()

    @pytest.mark.asyncio
    async def test_email_missing_recipient_is_permanent(self):
        t = EmailTransport(from_addr="bot@lf.test", sender=lambda msg: None)
        spec = NotificationSpec(
            tenant_id="t1", event_type="x", title="t", body="b",
            channels=[Channel.EMAIL],  # no user_email
        )
        with pytest.raises(ValueError):
            await t.send(spec)

    @pytest.mark.asyncio
    async def test_slack_payload_contains_title_and_body(self):
        posted: dict[str, Any] = {}

        async def poster(url: str, payload: dict) -> int:
            posted["url"] = url
            posted["payload"] = payload
            return 200

        t = SlackTransport(webhook_url="https://hook", poster=poster)
        await t.send(
            NotificationSpec(
                tenant_id="t1", event_type="order.updated",
                title="Order X updated", body="Body",
                channels=[Channel.SLACK], level="warning",
                order_id="ord-1",
            )
        )
        assert posted["url"] == "https://hook"
        assert "Order X updated" in posted["payload"]["text"]
        attachments = posted["payload"]["attachments"]
        assert attachments[0]["color"] == "#f59e0b"  # warning
        field_titles = [f["title"] for f in attachments[0]["fields"]]
        assert "event_type" in field_titles
        assert "order_id" in field_titles

    @pytest.mark.asyncio
    async def test_slack_5xx_is_transient(self):
        async def poster(url, payload):
            return 503

        t = SlackTransport(webhook_url="https://hook", poster=poster)
        with pytest.raises(TransientFailure):
            await t.send(
                NotificationSpec(
                    tenant_id="t1", event_type="x", title="t", body="b",
                    channels=[Channel.SLACK],
                )
            )

    @pytest.mark.asyncio
    async def test_slack_429_is_transient(self):
        async def poster(url, payload):
            return 429

        t = SlackTransport(webhook_url="https://hook", poster=poster)
        with pytest.raises(TransientFailure):
            await t.send(
                NotificationSpec(
                    tenant_id="t1", event_type="x", title="t", body="b",
                    channels=[Channel.SLACK],
                )
            )

    @pytest.mark.asyncio
    async def test_slack_400_is_permanent(self):
        async def poster(url, payload):
            return 400

        t = SlackTransport(webhook_url="https://hook", poster=poster)
        with pytest.raises(RuntimeError, match="permanent"):
            await t.send(
                NotificationSpec(
                    tenant_id="t1", event_type="x", title="t", body="b",
                    channels=[Channel.SLACK],
                )
            )

    @pytest.mark.asyncio
    async def test_pagerduty_payload_has_trigger_event(self):
        captured: dict[str, Any] = {}

        async def poster(url: str, payload: dict) -> int:
            captured["url"] = url
            captured["payload"] = payload
            return 202

        t = PagerDutyTransport(integration_key="key-123", poster=poster)
        await t.send(
            NotificationSpec(
                tenant_id="t1", event_type="hitl.escalated",
                title="SLA breached", body="Thread x escalated",
                channels=[Channel.PAGERDUTY], level="critical",
                order_id="ord-1",
            )
        )
        assert captured["payload"]["routing_key"] == "key-123"
        assert captured["payload"]["event_action"] == "trigger"
        assert captured["payload"]["payload"]["severity"] == "critical"
        # dedup_key groups retriggers of the same event/order
        assert "hitl.escalated" in captured["payload"]["dedup_key"]
        assert "ord-1" in captured["payload"]["dedup_key"]

    @pytest.mark.asyncio
    async def test_pagerduty_5xx_is_transient(self):
        async def poster(url, payload):
            return 500

        t = PagerDutyTransport(integration_key="key", poster=poster)
        with pytest.raises(TransientFailure):
            await t.send(
                NotificationSpec(
                    tenant_id="t1", event_type="x", title="t", body="b",
                    channels=[Channel.PAGERDUTY],
                )
            )

    @pytest.mark.asyncio
    async def test_in_app_writes_notification_row(self, session_factory):
        t = InAppTransport(session_factory=session_factory)
        await t.send(
            NotificationSpec(
                tenant_id="t1", event_type="cost_breaker.triggered",
                title="Title", body="Body", level="critical",
                channels=[Channel.IN_APP],
                user_id="u1", order_id="ord-1", item_no="item-2",
            )
        )
        async with session_factory() as s:
            rows = (await s.execute(select(NotificationModel))).scalars().all()
        assert len(rows) == 1
        n = rows[0]
        assert n.tenant_id == "t1"
        assert n.user_id == "u1"
        assert n.type == "cost_breaker.triggered"
        assert n.title == "Title"
        assert n.body == "Body"
        assert n.level == "critical"
        assert n.order_id == "ord-1"
        assert n.item_no == "item-2"
        assert n.is_read is False


# ── Protocol conformance ─────────────────────────────────────────────────────


def test_builtin_transports_conform_to_protocol():
    # Structural (Protocol) check — each built-in satisfies Transport.
    email = EmailTransport(from_addr="a@b", sender=lambda m: None)
    slack = SlackTransport(webhook_url="https://x")
    pager = PagerDutyTransport(integration_key="k")

    class DummyFactory:
        def __call__(self):
            raise NotImplementedError

    inapp = InAppTransport(session_factory=DummyFactory())
    for t in (email, slack, pager, inapp):
        assert isinstance(t, Transport)


# ── Singleton accessor ───────────────────────────────────────────────────────


class TestSingleton:
    def test_get_dispatcher_returns_same_instance(self):
        first = get_dispatcher()
        second = get_dispatcher()
        assert first is second

    def test_set_dispatcher_replaces(self):
        custom = NotificationDispatcher()
        set_dispatcher(custom)
        assert get_dispatcher() is custom

    def test_set_dispatcher_none_resets(self):
        first = get_dispatcher()
        set_dispatcher(None)
        second = get_dispatcher()
        assert first is not second


# ── End-to-end: dispatcher + real in-app transport ───────────────────────────


class TestDispatcherIntegration:
    @pytest.mark.asyncio
    async def test_in_app_via_dispatcher_writes_row_and_audit(
        self, session_factory, no_sleep
    ):
        d = NotificationDispatcher(
            transports=[InAppTransport(session_factory=session_factory)],
            audit_session_factory=session_factory,
            sleep=no_sleep,
        )
        await d.dispatch(
            NotificationSpec(
                tenant_id="t1", event_type="pipeline.failure",
                title="Pipeline failed", body="See logs",
                channels=[Channel.IN_APP], level="error",
            )
        )

        async with session_factory() as s:
            notifs = (await s.execute(select(NotificationModel))).scalars().all()
            audits = (await s.execute(select(AuditLog))).scalars().all()
        assert len(notifs) == 1
        assert notifs[0].type == "pipeline.failure"
        assert len(audits) == 1
        assert audits[0].action == "notification.sent"
