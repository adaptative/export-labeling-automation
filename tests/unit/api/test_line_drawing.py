"""Tests for Line Drawing Generator (TASK-027)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from labelforge.api.v1.auth import _make_stub_jwt
from labelforge.core.line_drawing import (
    DrawingConnectionManager,
    DrawingSession,
    DrawingValidationError,
    Stroke,
    drawing_manager,
    strokes_to_svg,
    validate_stroke,
)


# ── Core module unit tests ──────────────────────────────────────────────────


class TestValidateStroke:
    def test_accepts_list_of_pairs(self):
        stroke = validate_stroke({"points": [[0, 0], [10, 10]]})
        assert stroke.points == [(0.0, 0.0), (10.0, 10.0)]
        assert stroke.color == "#000000"
        assert stroke.width == 2.0

    def test_accepts_dict_points(self):
        stroke = validate_stroke(
            {"points": [{"x": 1, "y": 2}, {"x": 3, "y": 4}], "color": "#ff0000", "width": 5}
        )
        assert stroke.points == [(1.0, 2.0), (3.0, 4.0)]
        assert stroke.color == "#ff0000"
        assert stroke.width == 5.0

    def test_rejects_non_object(self):
        with pytest.raises(DrawingValidationError):
            validate_stroke("not an object")

    def test_rejects_empty_points(self):
        with pytest.raises(DrawingValidationError):
            validate_stroke({"points": []})

    def test_rejects_too_many_points(self):
        with pytest.raises(DrawingValidationError):
            validate_stroke({"points": [[i, i] for i in range(2001)]})

    def test_rejects_bad_width(self):
        with pytest.raises(DrawingValidationError):
            validate_stroke({"points": [[0, 0]], "width": 0})
        with pytest.raises(DrawingValidationError):
            validate_stroke({"points": [[0, 0]], "width": 101})

    def test_rejects_malformed_point(self):
        with pytest.raises(DrawingValidationError):
            validate_stroke({"points": [42]})


class TestStrokesToSvg:
    def test_valid_svg_shape(self):
        s = Stroke(points=[(0.0, 0.0), (10.0, 10.0)], color="#123456", width=3.0)
        svg = strokes_to_svg([s], width=100, height=100)
        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")
        assert 'xmlns="http://www.w3.org/2000/svg"' in svg
        assert "<path" in svg
        assert "#123456" in svg
        assert "M 0.00,0.00 L 10.00,10.00" in svg

    def test_empty_strokes_still_valid(self):
        svg = strokes_to_svg([])
        assert svg.startswith("<svg")
        assert "<path" not in svg


class TestDrawingSession:
    def test_add_and_snapshot(self):
        sess = DrawingSession(thread_id="t1")
        sess.add_stroke(Stroke(points=[(0.0, 0.0), (1.0, 1.0)]))
        snap = sess.snapshot()
        assert snap["stroke_count"] == 1
        assert snap["strokes"][0]["points"] == [[0.0, 0.0], [1.0, 1.0]]

    def test_clear_resets_strokes(self):
        sess = DrawingSession(thread_id="t1")
        sess.add_stroke(Stroke(points=[(0.0, 0.0)]))
        sess.clear()
        assert sess.strokes == []

    def test_render_svg_contains_strokes(self):
        sess = DrawingSession(thread_id="t1")
        sess.add_stroke(Stroke(points=[(0.0, 0.0), (5.0, 5.0)]))
        svg = sess.render_svg()
        assert "<path" in svg


# ── Connection manager ──────────────────────────────────────────────────────


class _FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_manager_broadcast_excludes_sender():
    mgr = DrawingConnectionManager()
    a, b, c = _FakeWS(), _FakeWS(), _FakeWS()
    await mgr.connect("room", a)
    await mgr.connect("room", b)
    await mgr.connect("room", c)
    sent = await mgr.broadcast("room", {"type": "stroke"}, exclude=a)
    assert sent == 2
    assert a.sent == []
    assert b.sent == [{"type": "stroke"}]
    assert c.sent == [{"type": "stroke"}]


@pytest.mark.asyncio
async def test_manager_broadcast_removes_dead_sockets():
    class _BrokenWS:
        async def send_json(self, payload):
            raise RuntimeError("boom")

    mgr = DrawingConnectionManager()
    broken = _BrokenWS()
    ok = _FakeWS()
    await mgr.connect("room", broken)
    await mgr.connect("room", ok)
    sent = await mgr.broadcast("room", {"x": 1})
    assert sent == 1
    assert mgr.peer_count("room") == 1


@pytest.mark.asyncio
async def test_manager_disconnect_cleans_empty_rooms():
    mgr = DrawingConnectionManager()
    ws = _FakeWS()
    await mgr.connect("room", ws)
    await mgr.disconnect("room", ws)
    assert mgr.peer_count("room") == 0


# ── REST / WebSocket integration ────────────────────────────────────────────


PREFIX = "/api/v1/hitl"


@pytest.fixture(autouse=True)
def _reset_drawing_manager():
    drawing_manager.reset()
    yield
    drawing_manager.reset()


async def _seed_thread() -> tuple[str, str, str]:
    """Attach a HiTL thread to the seeded order/item pair and return ids."""
    from labelforge.db import session as session_mod
    from labelforge.db.models import HiTLThreadModel

    tenant_id = "tnt-nakoda-001"
    order_id = "ORD-2026-0042"  # from seed data
    item_no = "A1001"  # from seed data
    thread_id = str(uuid4())

    async with session_mod.async_session_factory() as db:
        db.add(
            HiTLThreadModel(
                id=thread_id,
                tenant_id=tenant_id,
                order_id=order_id,
                item_no=item_no,
                agent_id="agent-test",
                priority="P2",
                status="OPEN",
            )
        )
        await db.commit()

    return thread_id, order_id, item_no


@pytest.fixture
def seeded_thread(client):
    import asyncio

    return asyncio.run(_seed_thread())


class TestDrawingREST:
    def test_get_drawing_empty_snapshot(self, client, admin_headers, seeded_thread):
        thread_id, _, _ = seeded_thread
        resp = client.get(f"{PREFIX}/threads/{thread_id}/drawing", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json() == {
            "thread_id": thread_id,
            "canvas_width": 800,
            "canvas_height": 600,
            "stroke_count": 0,
            "strokes": [],
        }

    def test_get_drawing_unauthenticated(self, client, seeded_thread):
        thread_id, _, _ = seeded_thread
        resp = client.get(f"{PREFIX}/threads/{thread_id}/drawing")
        assert resp.status_code == 401

    def test_get_drawing_unknown_thread_404(self, client, admin_headers):
        resp = client.get(
            f"{PREFIX}/threads/thread-does-not-exist/drawing", headers=admin_headers
        )
        assert resp.status_code == 404

    def test_finalize_empty_returns_409(self, client, admin_headers, seeded_thread):
        thread_id, _, _ = seeded_thread
        resp = client.post(
            f"{PREFIX}/threads/{thread_id}/drawing", headers=admin_headers
        )
        assert resp.status_code == 409

    def test_finalize_persists_artifact_and_message(
        self, client, admin_headers, seeded_thread
    ):
        thread_id, _, _ = seeded_thread
        # Pre-populate the session as if strokes had arrived via WS.
        sess = drawing_manager.session_for(thread_id)
        sess.add_stroke(Stroke(points=[(0.0, 0.0), (10.0, 10.0)], color="#000"))
        sess.add_stroke(Stroke(points=[(20.0, 20.0), (30.0, 30.0)], color="#f00"))

        resp = client.post(
            f"{PREFIX}/threads/{thread_id}/drawing", headers=admin_headers
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["stroke_count"] == 2
        assert body["svg_key"].startswith("hitl-drawings/")
        assert body["artifact_id"] is not None
        assert body["message_id"]
        assert len(body["content_hash"]) == 64  # sha256 hex

        # Message is now visible via the HiTL thread endpoint.
        thread_resp = client.get(f"/api/v1/hitl/threads/{thread_id}", headers=admin_headers)
        assert thread_resp.status_code == 200
        senders = [m["sender_type"] for m in thread_resp.json()["messages"]]
        assert "drawing" in senders

    def test_cross_tenant_thread_404(self, client, seeded_thread):
        thread_id, _, _ = seeded_thread
        other = _make_stub_jwt("usr-x", "tnt-other", "ADMIN", "x@x.com")
        resp = client.get(
            f"{PREFIX}/threads/{thread_id}/drawing",
            headers={"Authorization": f"Bearer {other}"},
        )
        assert resp.status_code == 404


class TestDrawingWebSocket:
    def test_ws_rejects_missing_token(self, client, seeded_thread):
        thread_id, _, _ = seeded_thread
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                f"{PREFIX}/threads/{thread_id}/drawing/ws"
            ):
                pass

    def test_ws_rejects_bad_token(self, client, seeded_thread):
        thread_id, _, _ = seeded_thread
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                f"{PREFIX}/threads/{thread_id}/drawing/ws?token=not-a-jwt"
            ):
                pass

    def test_ws_hello_includes_snapshot(self, client, seeded_thread, admin_token):
        thread_id, _, _ = seeded_thread
        with client.websocket_connect(
            f"{PREFIX}/threads/{thread_id}/drawing/ws?token={admin_token}"
        ) as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"
            assert hello["stroke_count"] == 0

    def test_ws_stroke_stored_in_session(self, client, seeded_thread, admin_token):
        thread_id, _, _ = seeded_thread
        with client.websocket_connect(
            f"{PREFIX}/threads/{thread_id}/drawing/ws?token={admin_token}"
        ) as ws:
            ws.receive_json()  # hello
            ws.send_json({"type": "stroke", "stroke": {"points": [[0, 0], [5, 5]]}})
            # No peers → no broadcast echo.  Just verify the session buffered.
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            assert pong == {"type": "pong"}
        assert len(drawing_manager.session_for(thread_id).strokes) == 1

    def test_ws_invalid_stroke_returns_error_frame(
        self, client, seeded_thread, admin_token
    ):
        thread_id, _, _ = seeded_thread
        with client.websocket_connect(
            f"{PREFIX}/threads/{thread_id}/drawing/ws?token={admin_token}"
        ) as ws:
            ws.receive_json()  # hello
            ws.send_json({"type": "stroke", "stroke": {"points": []}})
            err = ws.receive_json()
            assert err["type"] == "error"

    def test_ws_clear_empties_session(self, client, seeded_thread, admin_token):
        thread_id, _, _ = seeded_thread
        drawing_manager.session_for(thread_id).add_stroke(
            Stroke(points=[(0.0, 0.0), (1.0, 1.0)])
        )
        with client.websocket_connect(
            f"{PREFIX}/threads/{thread_id}/drawing/ws?token={admin_token}"
        ) as ws:
            ws.receive_json()  # hello
            ws.send_json({"type": "clear"})
            clear_echo = ws.receive_json()
            assert clear_echo["type"] == "clear"
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            assert pong == {"type": "pong"}
        assert drawing_manager.session_for(thread_id).strokes == []
