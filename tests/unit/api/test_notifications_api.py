"""Tests for /api/v1/notifications — Sprint-15 (INT-023).

Covers:
* PUT /{id}/read and PUT /read-all
* GET/PUT /users/me/notification-preferences
* WS /notifications/live (auth, hello, fan-out, pong, invalid token)
"""
from __future__ import annotations

import asyncio
import json
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from labelforge.api.v1.auth import _make_stub_jwt
from labelforge.api.v1 import notifications as notif_mod
from labelforge.db import session as session_mod
from labelforge.db.models import Notification as NotificationModel
from labelforge.services.hitl import InMemoryMessageRouter, set_message_router
from labelforge.services.hitl.router import make_envelope, EventType
from labelforge.services.notifications import (
    InMemoryPreferenceStore,
    NotificationDispatcher,
    get_dispatcher,
    set_dispatcher,
)


PREFIX = "/api/v1/notifications"


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_dispatcher():
    """Fresh dispatcher + preference store per test."""
    set_dispatcher(
        NotificationDispatcher(preferences=InMemoryPreferenceStore())
    )
    yield
    set_dispatcher(None)


@pytest.fixture(autouse=True)
def _isolate_router():
    r = InMemoryMessageRouter()
    set_message_router(r)
    yield r
    set_message_router(None)


async def _add_notification(**kwargs) -> str:
    """Insert a notification row through the patched session factory."""
    factory = session_mod.async_session_factory
    nid = kwargs.pop("id", f"notif-{int(time.time() * 1_000_000)}")
    async with factory() as s:
        s.add(
            NotificationModel(
                id=nid,
                tenant_id=kwargs.get("tenant_id", "tnt-nakoda-001"),
                user_id=kwargs.get("user_id"),
                type=kwargs.get("type", "system.alert"),
                title=kwargs.get("title", "Hello"),
                body=kwargs.get("body", "world"),
                level=kwargs.get("level", "info"),
                order_id=kwargs.get("order_id"),
                item_no=kwargs.get("item_no"),
                is_read=kwargs.get("is_read", False),
            )
        )
        await s.commit()
    return nid


# ── Mark-read endpoints ─────────────────────────────────────────────────────


class TestMarkRead:
    def test_mark_single_read(self, client, admin_headers):
        nid = asyncio.run(_add_notification(is_read=False))
        resp = client.put(f"{PREFIX}/{nid}/read", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"id": nid, "read": True}

        list_resp = client.get(f"{PREFIX}?read=false", headers=admin_headers)
        ids = [n["id"] for n in list_resp.json()["notifications"]]
        assert nid not in ids

    def test_mark_unknown_is_404(self, client, admin_headers):
        resp = client.put(f"{PREFIX}/does-not-exist/read", headers=admin_headers)
        assert resp.status_code == 404

    def test_mark_all(self, client, admin_headers):
        ids = [asyncio.run(_add_notification()) for _ in range(3)]
        resp = client.put(f"{PREFIX}/read-all", headers=admin_headers)
        assert resp.status_code == 200
        # Seed data may add its own rows; we only guarantee ours are marked.
        assert resp.json()["marked"] >= 3

        list_resp = client.get(f"{PREFIX}", headers=admin_headers)
        assert list_resp.json()["unread_count"] == 0

    def test_tenant_isolation(self, client, admin_headers):
        foreign = asyncio.run(_add_notification(tenant_id="other-tenant"))
        resp = client.put(f"{PREFIX}/{foreign}/read", headers=admin_headers)
        assert resp.status_code == 404

    def test_list_scoped_to_tenant(self, client, admin_headers):
        mine = asyncio.run(_add_notification(tenant_id="tnt-nakoda-001"))
        foreign = asyncio.run(_add_notification(tenant_id="other-tenant"))
        resp = client.get(f"{PREFIX}", headers=admin_headers)
        ids = [n["id"] for n in resp.json()["notifications"]]
        assert mine in ids
        # Never leak rows from other tenants (seed rows may be present).
        assert foreign not in ids
        for notif in resp.json()["notifications"]:
            # Implicit: tenant_id isn't exposed in the response, but the
            # foreign id is the only possible leak and we've asserted it's gone.
            pass


# ── Preferences ─────────────────────────────────────────────────────────────


USERS_PREFIX = "/api/v1/users/me/notification-preferences"


class TestPreferences:
    def test_get_returns_all_event_types_enabled_by_default(self, client, admin_headers):
        resp = client.get(USERS_PREFIX, headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert set(body["channels"]) >= {"email", "slack", "pagerduty", "in_app"}
        assert body["event_types"]
        # Every event enabled, every channel on.
        for pref in body["preferences"]:
            assert pref["enabled"] is True
            ch = pref["channels"]
            assert ch["email"] is True
            assert ch["slack"] is True

    def test_put_mutes_channel_for_event(self, client, admin_headers):
        resp = client.put(
            USERS_PREFIX,
            headers=admin_headers,
            json={
                "preferences": [
                    {
                        "event_type": "cost_breaker.triggered",
                        "enabled": True,
                        "channels": {
                            "email": True,
                            "slack": False,
                            "pagerduty": True,
                            "in_app": True,
                        },
                    }
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        cost = next(p for p in body["preferences"] if p["event_type"] == "cost_breaker.triggered")
        assert cost["channels"]["slack"] is False
        assert cost["channels"]["email"] is True

    def test_put_disable_event_mutes_every_channel(self, client, admin_headers):
        resp = client.put(
            USERS_PREFIX,
            headers=admin_headers,
            json={
                "preferences": [
                    {
                        "event_type": "order.completed",
                        "enabled": False,
                        "channels": {"email": True, "slack": True, "pagerduty": True, "in_app": True},
                    }
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        order = next(p for p in body["preferences"] if p["event_type"] == "order.completed")
        assert order["enabled"] is False
        for on in order["channels"].values():
            assert on is False

    def test_put_requires_auth(self, client):
        resp = client.put(
            USERS_PREFIX,
            json={"preferences": []},
        )
        assert resp.status_code == 401

    def test_per_tenant_isolation(self, client, admin_headers):
        # Admin mutes slack for cost breaker…
        client.put(
            USERS_PREFIX,
            headers=admin_headers,
            json={
                "preferences": [
                    {
                        "event_type": "cost_breaker.triggered",
                        "enabled": True,
                        "channels": {"email": True, "slack": False, "pagerduty": True, "in_app": True},
                    }
                ]
            },
        )

        # …a user from a different tenant sees defaults (slack on).
        other_token = _make_stub_jwt("usr-2", "tnt-other-001", "ADMIN", "a@b.com")
        other_headers = {"Authorization": f"Bearer {other_token}"}
        resp = client.get(USERS_PREFIX, headers=other_headers)
        cost = next(p for p in resp.json()["preferences"] if p["event_type"] == "cost_breaker.triggered")
        assert cost["channels"]["slack"] is True


# ── WebSocket ──────────────────────────────────────────────────────────────


class TestNotificationWebSocket:
    def test_rejects_without_token(self, client):
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/api/v1/notifications/live"):
                pass
        assert exc_info.value.code == 4401

    def test_rejects_bad_token(self, client):
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/api/v1/notifications/live?token=bad"):
                pass
        assert exc_info.value.code == 4401

    def test_accepts_valid_token_and_sends_hello(self, client, admin_token):
        with client.websocket_connect(
            f"/api/v1/notifications/live?token={admin_token}"
        ) as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"
            assert hello["payload"]["user_id"] == "usr-admin-001"
            assert hello["payload"]["tenant_id"] == "tnt-nakoda-001"

    def test_pong_in_response_to_ping(self, client, admin_token):
        with client.websocket_connect(
            f"/api/v1/notifications/live?token={admin_token}"
        ) as ws:
            ws.receive_json()  # hello
            ws.send_json({"type": "ping"})
            reply = ws.receive_json()
            assert reply["type"] == "pong"

    def test_receives_published_notification(self, client, admin_token, _isolate_router):
        channel = notif_mod.USER_NOTIFICATION_CHANNEL.format(user_id="usr-admin-001")
        with client.websocket_connect(
            f"/api/v1/notifications/live?token={admin_token}"
        ) as ws:
            ws.receive_json()  # hello
            envelope = make_envelope(
                "notification_received",
                channel,
                {
                    "id": "notif-1",
                    "title": "Cost breaker triggered",
                    "severity": "critical",
                },
            )
            # Publish via the router the server is subscribed to.
            asyncio.run(_isolate_router.publish(channel, envelope))
            msg = ws.receive_json()
            assert msg["type"] == "notification_received"
            assert msg["payload"]["id"] == "notif-1"
