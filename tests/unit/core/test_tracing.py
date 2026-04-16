"""Tests for labelforge.core.tracing (Sprint-16, TASK-040)."""
from __future__ import annotations

import pytest

from labelforge.core import tracing


@pytest.fixture(autouse=True)
def _reset_tracing_state():
    """Reset module-level state so each test starts fresh."""
    tracing._CONFIGURED = False
    tracing._PROVIDER = None
    yield
    tracing._CONFIGURED = False
    tracing._PROVIDER = None


# ── configure_tracing ────────────────────────────────────────────────────────


class TestConfigureTracing:
    def test_returns_provider_when_available(self):
        provider = tracing.configure_tracing("labelforge-test")
        if tracing.OTEL_AVAILABLE:
            assert provider is not None
            assert tracing._CONFIGURED is True
            assert tracing._SERVICE_NAME == "labelforge-test"
        else:
            assert provider is None

    def test_is_idempotent(self):
        p1 = tracing.configure_tracing("svc-a")
        p2 = tracing.configure_tracing("svc-b")
        # Second call returns the already-installed provider unchanged.
        assert p1 is p2
        # Service name is pinned by the first call.
        assert tracing._SERVICE_NAME == "svc-a"

    def test_console_flag_attaches_processor(self):
        if not tracing.OTEL_AVAILABLE:
            pytest.skip("OTel not installed")
        provider = tracing.configure_tracing("labelforge", console=True)
        assert provider is not None
        # At least one span processor registered for the console exporter.
        processors = getattr(provider, "_active_span_processor", None)
        assert processors is not None

    def test_env_otlp_endpoint_picks_otlp(self, monkeypatch):
        if not tracing.OTEL_AVAILABLE:
            pytest.skip("OTel not installed")
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces")
        # Should not raise even if endpoint unreachable (exporter is created lazily).
        provider = tracing.configure_tracing("labelforge-otlp")
        assert provider is not None

    def test_no_otel_returns_none(self, monkeypatch):
        """Simulated missing-OTel path via flag override."""
        monkeypatch.setattr(tracing, "OTEL_AVAILABLE", False)
        tracing._CONFIGURED = False
        provider = tracing.configure_tracing("stripped-env")
        assert provider is None
        assert tracing._CONFIGURED is True


# ── get_tracer / get_trace_context ──────────────────────────────────────────


class TestGetTracer:
    def test_get_tracer_returns_object(self):
        t = tracing.get_tracer("labelforge.tests")
        assert t is not None
        # Either a real OTel tracer or the NoopTracer shim.
        assert hasattr(t, "start_as_current_span")

    def test_trace_context_none_outside_span(self):
        tracing.configure_tracing("labelforge-ctx-test")
        trace_id, span_id = tracing.get_trace_context()
        # Outside of any active span we should get None/None.
        assert trace_id is None
        assert span_id is None

    def test_trace_context_inside_span(self):
        if not tracing.OTEL_AVAILABLE:
            pytest.skip("OTel not installed")
        tracing.configure_tracing("labelforge-ctx")
        tracer = tracing.get_tracer("labelforge.tests")
        with tracer.start_as_current_span("test.span"):
            trace_id, span_id = tracing.get_trace_context()
            assert trace_id is not None
            assert span_id is not None
            assert len(trace_id) == 32
            assert len(span_id) == 16
        # Outside the span context again — should be None.
        assert tracing.get_trace_context() == (None, None)

    def test_noop_fallback_returns_none_none(self, monkeypatch):
        monkeypatch.setattr(tracing, "OTEL_AVAILABLE", False)
        assert tracing.get_trace_context() == (None, None)


# ── Instrumentation helpers ──────────────────────────────────────────────────


class TestInstrumentation:
    def test_instrument_fastapi_no_raise(self):
        from fastapi import FastAPI

        app = FastAPI()
        # Should succeed (or silently no-op) without raising.
        tracing.instrument_fastapi(app)

    def test_instrument_sqlalchemy_no_raise(self):
        # Pass a dummy object — helper handles missing ``sync_engine`` attr.
        tracing.instrument_sqlalchemy(object())

    def test_instrument_httpx_no_raise(self):
        tracing.instrument_httpx()

    def test_instrument_logging_no_raise(self):
        tracing.instrument_logging()

    def test_no_otel_instrument_is_noop(self, monkeypatch):
        monkeypatch.setattr(tracing, "OTEL_AVAILABLE", False)
        # Every helper should be a pure no-op in stripped envs.
        tracing.instrument_fastapi(object())
        tracing.instrument_sqlalchemy(object())
        tracing.instrument_httpx()
        tracing.instrument_logging()


# ── mark_error + noop spans ─────────────────────────────────────────────────


class TestMarkError:
    def test_mark_error_on_real_span(self):
        if not tracing.OTEL_AVAILABLE:
            pytest.skip("OTel not installed")
        tracing.configure_tracing("labelforge-err")
        tracer = tracing.get_tracer("labelforge.tests")
        with tracer.start_as_current_span("err.span") as span:
            tracing.mark_error(span, RuntimeError("boom"))
            # The span should now report ERROR status.
            status = span.status
            # status.status_code is the OTel enum; str(.name) == "ERROR".
            assert getattr(status, "status_code", None) is not None
            assert status.status_code.name == "ERROR"

    def test_mark_error_on_none_span_is_safe(self):
        tracing.mark_error(None, ValueError("x"))  # must not raise

    def test_mark_error_no_otel(self, monkeypatch):
        monkeypatch.setattr(tracing, "OTEL_AVAILABLE", False)
        tracing.mark_error(tracing._NoopSpan(), RuntimeError("noop"))

    def test_noop_span_context_manager(self):
        span = tracing._NoopSpan()
        with span as s:
            s.set_attribute("k", "v")
            s.set_status("ok")
            s.record_exception(RuntimeError("x"))
            s.add_event("evt")
            s.end()

    def test_noop_tracer_starts_span(self):
        t = tracing._NoopTracer()
        with t.start_as_current_span("x") as span:
            assert span is not None
        assert t.start_span("y") is not None
