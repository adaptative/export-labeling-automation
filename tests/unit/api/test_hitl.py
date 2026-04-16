"""REST + WebSocket tests for /api/v1/hitl (Sprint-14)."""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from labelforge.api.v1 import hitl as hitl_mod
from labelforge.api.v1.auth import _make_stub_jwt
from labelforge.db import session as session_mod
from labelforge.db.models import AuditLog, HiTLMessageModel, HiTLThreadModel, Notification
from labelforge.services.hitl import (
    InMemoryMessageRouter,
    set_escalation_notifier,
    set_message_router,
    set_thread_resolver,
    set_workflow_resumer,
    ThreadResolver,
)


PREFIX = "/api/v1/hitl"


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_router():
    """Fresh in-memory router + resolver per test — no bleed between cases."""
    r = InMemoryMessageRouter()
    set_message_router(r)
    set_thread_resolver(ThreadResolver(router=r))
    set_escalation_notifier(None)
    set_workflow_resumer(None)
    yield r
    set_message_router(None)
    set_thread_resolver(None)
    set_escalation_notifier(None)
    set_workflow_resumer(None)


def _create_thread(client, admin_headers, *, priority: str = "P2",
                   initial: str | None = None) -> str:
    """Create a thread through the REST API and return its id."""
    resp = client.post(
        f"{PREFIX}/threads",
        json={
            "order_id": "ORD-2026-0042",
            "item_no": "A1001",
            "agent_id": "fusion-agent",
            "priority": priority,
            "initial_message": initial,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["thread_id"]


# ── Thread creation ─────────────────────────────────────────────────────────


class TestCreateThreadEndpoint:
    def test_creates_thread_with_sla(self, client, admin_headers):
        resp = client.post(
            f"{PREFIX}/threads",
            json={
                "order_id": "ORD-2026-0042",
                "item_no": "A1001",
                "agent_id": "fusion-agent",
                "priority": "P0",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "OPEN"
        assert body["priority"] == "P0"
        assert body["sla_deadline"]  # not empty
        assert body["thread_id"]

    def test_invalid_priority_rejected(self, client, admin_headers):
        resp = client.post(
            f"{PREFIX}/threads",
            json={
                "order_id": "ORD-2026-0042",
                "item_no": "A1001",
                "agent_id": "fusion-agent",
                "priority": "P99",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_requires_auth(self, client):
        resp = client.post(f"{PREFIX}/threads", json={
            "order_id": "ORD-2026-0042", "item_no": "A1001",
            "agent_id": "fusion", "priority": "P2",
        })
        assert resp.status_code == 401


# ── Thread list filters ─────────────────────────────────────────────────────


class TestThreadListFilters:
    def test_filters_by_status(self, client, admin_headers):
        _create_thread(client, admin_headers, priority="P2")
        tid2 = _create_thread(client, admin_headers, priority="P1")
        # Resolve one to differentiate status.
        r = client.post(f"{PREFIX}/threads/{tid2}/resolve",
                        json={"note": "ok"}, headers=admin_headers)
        assert r.status_code == 200

        open_resp = client.get(f"{PREFIX}/threads?status=OPEN", headers=admin_headers)
        resolved_resp = client.get(f"{PREFIX}/threads?status=RESOLVED", headers=admin_headers)
        assert open_resp.status_code == 200
        assert resolved_resp.status_code == 200
        assert all(t["status"] == "OPEN" for t in open_resp.json()["threads"])
        assert all(t["status"] == "RESOLVED" for t in resolved_resp.json()["threads"])

    def test_invalid_status_filter_400(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/threads?status=WEIRD", headers=admin_headers)
        assert resp.status_code == 400

    def test_filters_by_priority(self, client, admin_headers):
        _create_thread(client, admin_headers, priority="P0")
        _create_thread(client, admin_headers, priority="P2")
        p0 = client.get(f"{PREFIX}/threads?priority=P0", headers=admin_headers)
        assert p0.status_code == 200
        assert all(t["priority"] == "P0" for t in p0.json()["threads"])


# ── Messages + option-select ────────────────────────────────────────────────


class TestMessages:
    def test_paginated_message_list(self, client, admin_headers):
        tid = _create_thread(client, admin_headers, initial="Please confirm")
        for i in range(3):
            r = client.post(
                f"{PREFIX}/threads/{tid}/messages",
                json={"sender_type": "human", "content": f"reply {i}"},
                headers=admin_headers,
            )
            assert r.status_code == 201, r.text
        resp = client.get(f"{PREFIX}/threads/{tid}/messages", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        # 1 initial agent + 3 human = 4.
        assert body["total"] == 4
        assert len(body["messages"]) == 4
        # Messages sorted oldest-first.
        contents = [m["content"] for m in body["messages"]]
        assert contents[0] == "Please confirm"

    def test_message_list_unknown_thread_404(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/threads/does-not-exist/messages", headers=admin_headers)
        assert resp.status_code == 404

    def test_option_select_persists_and_transitions(self, client, admin_headers):
        tid = _create_thread(client, admin_headers)
        resp = client.post(
            f"{PREFIX}/threads/{tid}/option-select",
            json={"option_index": 1, "option_value": "Use PI value"},
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["context"]["option_index"] == 1
        assert body["context"]["option_value"] == "Use PI value"

        # Thread status moved to IN_PROGRESS.
        thr = client.get(f"{PREFIX}/threads/{tid}", headers=admin_headers).json()
        assert thr["thread"]["status"] == "IN_PROGRESS"

    def test_option_select_on_resolved_thread_409(self, client, admin_headers):
        tid = _create_thread(client, admin_headers)
        client.post(f"{PREFIX}/threads/{tid}/resolve", json={}, headers=admin_headers)
        resp = client.post(
            f"{PREFIX}/threads/{tid}/option-select",
            json={"option_index": 0},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    def test_add_message_rejects_empty_content(self, client, admin_headers):
        tid = _create_thread(client, admin_headers)
        resp = client.post(
            f"{PREFIX}/threads/{tid}/messages",
            json={"content": ""},
            headers=admin_headers,
        )
        assert resp.status_code == 422  # pydantic validation

    def test_add_message_cross_tenant_404(self, client, admin_headers):
        tid = _create_thread(client, admin_headers)
        other = _make_stub_jwt("usr-x", "tnt-other", "ADMIN", "x@x.com")
        resp = client.post(
            f"{PREFIX}/threads/{tid}/messages",
            json={"content": "sneak"},
            headers={"Authorization": f"Bearer {other}"},
        )
        assert resp.status_code == 404


# ── Resolve / Escalate ─────────────────────────────────────────────────────


class TestResolveEndpoint:
    def test_resolve_sets_status(self, client, admin_headers):
        tid = _create_thread(client, admin_headers)
        resp = client.post(
            f"{PREFIX}/threads/{tid}/resolve",
            json={"note": "Decided net weight = 0.80"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["thread"]["status"] == "RESOLVED"

    def test_resolve_writes_audit(self, client, admin_headers):
        tid = _create_thread(client, admin_headers)
        client.post(f"{PREFIX}/threads/{tid}/resolve",
                    json={"note": "ok"}, headers=admin_headers)

        async def _check():
            async with session_mod.async_session_factory() as db:
                rows = (await db.execute(
                    select(AuditLog).where(
                        AuditLog.action == "hitl_thread_resolved",
                        AuditLog.resource_id == tid,
                    )
                )).scalars().all()
                assert len(rows) == 1
        asyncio.run(_check())

    def test_resolve_twice_409(self, client, admin_headers):
        tid = _create_thread(client, admin_headers)
        client.post(f"{PREFIX}/threads/{tid}/resolve", json={}, headers=admin_headers)
        again = client.post(f"{PREFIX}/threads/{tid}/resolve", json={}, headers=admin_headers)
        assert again.status_code == 409

    def test_resolve_unknown_404(self, client, admin_headers):
        resp = client.post(f"{PREFIX}/threads/missing/resolve",
                           json={}, headers=admin_headers)
        assert resp.status_code == 404


class TestEscalateEndpoint:
    def test_escalate_sets_status_and_notifies(self, client, admin_headers):
        calls = []

        async def _notify(thread, reason):
            calls.append((thread.id, reason))

        set_escalation_notifier(_notify)

        tid = _create_thread(client, admin_headers)
        resp = client.post(
            f"{PREFIX}/threads/{tid}/escalate",
            json={"reason": "No owner for 30 min"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["thread"]["status"] == "ESCALATED"
        assert calls == [(tid, "No owner for 30 min")]

    def test_escalate_writes_notification(self, client, admin_headers):
        tid = _create_thread(client, admin_headers)
        client.post(
            f"{PREFIX}/threads/{tid}/escalate",
            json={"reason": "Critical"},
            headers=admin_headers,
        )

        async def _check():
            async with session_mod.async_session_factory() as db:
                rows = (await db.execute(
                    select(Notification).where(Notification.type == "hitl_escalation")
                )).scalars().all()
                assert len(rows) >= 1
        asyncio.run(_check())

    def test_escalate_rejects_empty_reason(self, client, admin_headers):
        tid = _create_thread(client, admin_headers)
        resp = client.post(
            f"{PREFIX}/threads/{tid}/escalate",
            json={"reason": ""},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_escalate_twice_409(self, client, admin_headers):
        tid = _create_thread(client, admin_headers)
        client.post(f"{PREFIX}/threads/{tid}/escalate",
                    json={"reason": "x"}, headers=admin_headers)
        again = client.post(f"{PREFIX}/threads/{tid}/escalate",
                            json={"reason": "x"}, headers=admin_headers)
        assert again.status_code == 409


# ── WebSocket ───────────────────────────────────────────────────────────────


class TestThreadLiveWebSocket:
    def test_rejects_missing_token(self, client, admin_headers):
        tid = _create_thread(client, admin_headers)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"{PREFIX}/threads/{tid}/live"):
                pass

    def test_rejects_bad_token(self, client, admin_headers):
        tid = _create_thread(client, admin_headers)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                f"{PREFIX}/threads/{tid}/live?token=not-a-jwt"
            ):
                pass

    def test_rejects_unknown_thread(self, client, admin_token):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                f"{PREFIX}/threads/does-not-exist/live?token={admin_token}"
            ):
                pass

    def test_rejects_cross_tenant_thread(self, client, admin_headers):
        tid = _create_thread(client, admin_headers)
        other = _make_stub_jwt("usr-x", "tnt-other", "ADMIN", "x@x.com")
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                f"{PREFIX}/threads/{tid}/live?token={other}"
            ):
                pass

    def test_hello_frame_has_thread_context(self, client, admin_headers, admin_token):
        tid = _create_thread(client, admin_headers)
        with client.websocket_connect(
            f"{PREFIX}/threads/{tid}/live?token={admin_token}"
        ) as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"
            assert hello["thread_id"] == tid
            assert hello["payload"]["status"] == "OPEN"
            assert hello["payload"]["order_id"] == "ORD-2026-0042"

    def test_ping_pong(self, client, admin_headers, admin_token):
        tid = _create_thread(client, admin_headers)
        with client.websocket_connect(
            f"{PREFIX}/threads/{tid}/live?token={admin_token}"
        ) as ws:
            ws.receive_json()  # hello
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            assert pong["type"] == "pong"

    def test_message_frame_persists_and_broadcasts(
        self, client, admin_headers, admin_token,
    ):
        tid = _create_thread(client, admin_headers)
        with client.websocket_connect(
            f"{PREFIX}/threads/{tid}/live?token={admin_token}"
        ) as ws:
            ws.receive_json()  # hello
            ws.send_json({
                "type": "message",
                "content": "Checking logs now",
                "sender_type": "human",
            })
            # Expect at least one envelope back: human_message (and maybe
            # a status_update when OPEN→IN_PROGRESS).
            seen: list[dict] = []
            for _ in range(2):
                try:
                    seen.append(ws.receive_json())
                except Exception:
                    break
            types = [e["type"] for e in seen]
            assert "human_message" in types

        # Verify persistence.
        async def _check():
            async with session_mod.async_session_factory() as db:
                rows = (await db.execute(
                    select(HiTLMessageModel).where(HiTLMessageModel.thread_id == tid)
                )).scalars().all()
                contents = [r.content for r in rows]
                assert "Checking logs now" in contents
        asyncio.run(_check())

    def test_option_selected_frame_persists(
        self, client, admin_headers, admin_token,
    ):
        tid = _create_thread(client, admin_headers)
        with client.websocket_connect(
            f"{PREFIX}/threads/{tid}/live?token={admin_token}"
        ) as ws:
            ws.receive_json()  # hello
            ws.send_json({
                "type": "option_selected",
                "option_index": 2,
                "option_value": "Use PI value",
            })
            seen: list[dict] = []
            for _ in range(2):
                try:
                    seen.append(ws.receive_json())
                except Exception:
                    break
            assert any(e["type"] == "option_selected" for e in seen)

    def test_typing_broadcasts_without_persistence(
        self, client, admin_headers, admin_token,
    ):
        tid = _create_thread(client, admin_headers)
        with client.websocket_connect(
            f"{PREFIX}/threads/{tid}/live?token={admin_token}"
        ) as ws:
            ws.receive_json()  # hello
            ws.send_json({"type": "typing", "is_typing": True})
            env = ws.receive_json()
            assert env["type"] == "typing"
            assert env["payload"]["is_typing"] is True

        # No message row persisted for typing indicator.
        async def _check():
            async with session_mod.async_session_factory() as db:
                rows = (await db.execute(
                    select(HiTLMessageModel).where(HiTLMessageModel.thread_id == tid)
                )).scalars().all()
                # Thread was created without an initial message, so zero rows.
                assert len(rows) == 0
        asyncio.run(_check())

    def test_rest_resolve_broadcasts_to_ws(
        self, client, admin_headers, admin_token,
    ):
        tid = _create_thread(client, admin_headers)
        with client.websocket_connect(
            f"{PREFIX}/threads/{tid}/live?token={admin_token}"
        ) as ws:
            ws.receive_json()  # hello
            r = client.post(f"{PREFIX}/threads/{tid}/resolve",
                            json={"note": "decided"}, headers=admin_headers)
            assert r.status_code == 200
            env = ws.receive_json()
            assert env["type"] == "thread_resolved"
            assert env["payload"]["status"] == "RESOLVED"

    def test_bad_frame_returns_error_without_crash(
        self, client, admin_headers, admin_token,
    ):
        tid = _create_thread(client, admin_headers)
        with client.websocket_connect(
            f"{PREFIX}/threads/{tid}/live?token={admin_token}"
        ) as ws:
            ws.receive_json()  # hello
            ws.send_json({"type": "message", "content": ""})  # empty → error
            env = ws.receive_json()
            assert env["type"] == "error"
            # Socket still alive — follow-up ping works.
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            assert pong["type"] == "pong"
