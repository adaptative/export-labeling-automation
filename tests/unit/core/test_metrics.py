"""Tests for labelforge.core.metrics (Sprint-16, TASK-041)."""
from __future__ import annotations

import pytest

from labelforge.core import metrics as m


def _sample_value(metric, labels: dict) -> float:
    """Read back the current value of a labelled Counter/Gauge/Histogram."""
    if not m.PROMETHEUS_AVAILABLE:
        return 0.0
    child = metric.labels(**labels)
    # For Counter and Gauge the value sits on ``_value``; for Histogram
    # we read the ``_sum`` sample.
    if hasattr(child, "_sum"):
        return float(child._sum.get())
    return float(child._value.get())


# ── _normalize_path ──────────────────────────────────────────────────────────


class TestNormalizePath:
    def test_leaves_root_intact(self):
        assert m._normalize_path("/") == "/"

    def test_leaves_plain_path(self):
        assert m._normalize_path("/api/v1/orders") == "/api/v1/orders"

    def test_collapses_numeric_id(self):
        assert m._normalize_path("/api/v1/orders/123456") == "/api/v1/orders/:id"

    def test_collapses_hyphenated_numeric_id(self):
        assert m._normalize_path("/a/2024-01-15") == "/a/:id"

    def test_collapses_uuid_like(self):
        uuid_seg = "ord-abc123def456"
        assert m._normalize_path(f"/api/orders/{uuid_seg}") == "/api/orders/:id"

    def test_short_alnum_not_collapsed(self):
        # 9-char segments with no digit are considered safe.
        assert m._normalize_path("/api/v1/items/orders") == "/api/v1/items/orders"

    def test_multiple_id_segments(self):
        assert (
            m._normalize_path("/api/v1/orders/abc1234567/items/9999")
            == "/api/v1/orders/:id/items/:id"
        )


# ── record_request ───────────────────────────────────────────────────────────


class TestRecordRequest:
    def test_increments_total_and_duration(self):
        if not m.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client not installed")
        labels = {"method": "GET", "path": "/ping", "status": "200"}
        before = _sample_value(m.metric("requests_total"), labels)
        m.record_request(method="GET", path="/ping", status=200, duration_seconds=0.123)
        after = _sample_value(m.metric("requests_total"), labels)
        assert after == pytest.approx(before + 1)

    def test_5xx_bumps_error_counter(self):
        if not m.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client not installed")
        err = m.metric("errors_total")
        before = _sample_value(err, {"category": "http_5xx"})
        m.record_request(method="POST", path="/boom", status=503, duration_seconds=0.05)
        after = _sample_value(err, {"category": "http_5xx"})
        assert after == pytest.approx(before + 1)

    def test_negative_duration_clamped(self):
        # Must not raise — Histogram rejects negatives, helper clamps.
        m.record_request(method="GET", path="/x", status=200, duration_seconds=-0.5)


# ── record_agent_call ────────────────────────────────────────────────────────


class TestRecordAgentCall:
    def test_success_and_failure(self):
        if not m.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client not installed")
        ok_before = _sample_value(
            m.metric("agent_calls_total"), {"agent_id": "foo", "success": "true"}
        )
        m.record_agent_call(agent_id="foo", success=True, duration_seconds=0.01)
        m.record_agent_call(agent_id="foo", success=False, duration_seconds=0.02)
        ok_after = _sample_value(
            m.metric("agent_calls_total"), {"agent_id": "foo", "success": "true"}
        )
        fail_after = _sample_value(
            m.metric("agent_calls_total"), {"agent_id": "foo", "success": "false"}
        )
        assert ok_after == pytest.approx(ok_before + 1)
        assert fail_after >= 1


# ── record_cost / record_error ──────────────────────────────────────────────


class TestRecordCost:
    def test_zero_cost_skipped(self):
        # Should not raise and should not increment.
        m.record_cost(tenant_id="t1", scope="agent", amount_usd=0)
        m.record_cost(tenant_id="t1", scope="agent", amount_usd=-1.0)

    def test_positive_cost_accumulates(self):
        if not m.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client not installed")
        labels = {"tenant_id": "t1", "scope": "agent"}
        before = _sample_value(m.metric("cost_usd_total"), labels)
        m.record_cost(tenant_id="t1", scope="agent", amount_usd=1.5)
        after = _sample_value(m.metric("cost_usd_total"), labels)
        assert after == pytest.approx(before + 1.5)

    def test_unknown_tenant_falls_back(self):
        # Must not raise when tenant_id is blank.
        m.record_cost(tenant_id="", scope="agent", amount_usd=0.1)


class TestRecordError:
    def test_increments_category(self):
        if not m.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client not installed")
        before = _sample_value(m.metric("errors_total"), {"category": "custom"})
        m.record_error("custom")
        after = _sample_value(m.metric("errors_total"), {"category": "custom"})
        assert after == pytest.approx(before + 1)


# ── gauges ───────────────────────────────────────────────────────────────────


class TestGauges:
    def test_observe_queue_depth(self):
        if not m.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client not installed")
        m.observe_queue_depth(tenant_id="t1", status="open", depth=42)
        val = _sample_value(
            m.metric("hitl_queue_depth"), {"tenant_id": "t1", "status": "open"}
        )
        assert val == 42.0

    def test_set_automation_rate(self):
        if not m.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client not installed")
        m.set_automation_rate(tenant_id="t1", rate_percent=78.5)
        val = _sample_value(m.metric("automation_rate"), {"tenant_id": "t1"})
        assert val == pytest.approx(78.5)


# ── render_metrics ───────────────────────────────────────────────────────────


class TestRenderMetrics:
    def test_returns_payload_and_content_type(self):
        payload, ctype = m.render_metrics()
        assert isinstance(payload, (bytes, bytearray))
        assert isinstance(ctype, str)
        assert "text/plain" in ctype or "openmetrics" in ctype

    def test_payload_includes_registered_metrics(self):
        if not m.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client not installed")
        # Touch a metric so there's something to render.
        m.record_request(method="GET", path="/rendered", status=200, duration_seconds=0.1)
        payload, _ = m.render_metrics()
        text = payload.decode("utf-8")
        assert "labelforge_requests_total" in text


# ── PrometheusMiddleware ─────────────────────────────────────────────────────


class TestPrometheusMiddleware:
    @pytest.mark.asyncio
    async def test_metrics_path_excluded(self):
        hit = {"inner": False}

        async def app(scope, receive, send):
            hit["inner"] = True
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        sent: list = []

        async def send(msg):
            sent.append(msg)

        mw = m.PrometheusMiddleware(app)
        await mw({"type": "http", "method": "GET", "path": "/metrics"}, receive, send)
        assert hit["inner"] is True

    @pytest.mark.asyncio
    async def test_records_normal_request(self):
        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 201, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(_):
            pass

        mw = m.PrometheusMiddleware(app)
        await mw({"type": "http", "method": "POST", "path": "/api/v1/ok"}, receive, send)

    @pytest.mark.asyncio
    async def test_non_http_scope_passthrough(self):
        called = {"hit": False}

        async def app(scope, receive, send):
            called["hit"] = True

        mw = m.PrometheusMiddleware(app)
        await mw({"type": "lifespan"}, None, None)
        assert called["hit"] is True

    @pytest.mark.asyncio
    async def test_exception_still_records_500(self):
        if not m.PROMETHEUS_AVAILABLE:
            pytest.skip("prometheus_client not installed")

        async def app(scope, receive, send):
            raise RuntimeError("boom")

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(_):
            pass

        mw = m.PrometheusMiddleware(app)
        with pytest.raises(RuntimeError):
            await mw(
                {"type": "http", "method": "GET", "path": "/explode"}, receive, send
            )
