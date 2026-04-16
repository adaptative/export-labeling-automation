"""OpenTelemetry distributed tracing (TASK-040).

All tracing in labelforge is routed through the OTel SDK. Calling
:func:`configure_tracing` once at startup installs a tracer provider,
configures the OTLP/HTTP exporter (if ``OTEL_EXPORTER_OTLP_ENDPOINT`` is
set) and auto-instruments FastAPI, SQLAlchemy, and httpx.

Public surface
--------------

* ``configure_tracing(service_name=...)`` — idempotent. Returns the
  installed ``TracerProvider``.
* ``get_tracer(name)`` — shortcut for ``trace.get_tracer``.
* ``instrument_fastapi(app)`` — call after ``FastAPI()`` to wire
  request spans and propagation.
* ``instrument_sqlalchemy(engine)`` — attach a span per query.
* ``get_trace_context()`` — returns ``(trace_id_hex, span_id_hex)``
  for the current span, or ``(None, None)`` when no span is active.

The module fails soft: missing OTel packages (e.g. in minimal test
envs) downgrade to no-op wrappers without raising, so production and
CI can share the same call sites.
"""
from __future__ import annotations

import os
from typing import Any, Optional, Tuple

_LOG = None  # lazy — avoids import loop with labelforge.core.logging


def _lazy_log() -> Any:
    global _LOG
    if _LOG is None:
        from labelforge.core.logging import get_logger

        _LOG = get_logger(__name__)
    return _LOG


# ── OTel imports (best-effort) ───────────────────────────────────────────────

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )
    from opentelemetry.trace import Span, SpanKind, Status, StatusCode

    OTEL_AVAILABLE = True
except Exception:  # pragma: no cover — only in stripped envs
    trace = None  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment]
    BatchSpanProcessor = None  # type: ignore[assignment]
    ConsoleSpanExporter = None  # type: ignore[assignment]
    SimpleSpanProcessor = None  # type: ignore[assignment]
    Span = Any  # type: ignore[assignment]
    SpanKind = None  # type: ignore[assignment]
    Status = None  # type: ignore[assignment]
    StatusCode = None  # type: ignore[assignment]
    OTEL_AVAILABLE = False


# ── Module state ─────────────────────────────────────────────────────────────

_CONFIGURED = False
_PROVIDER: Optional[Any] = None
_SERVICE_NAME = "labelforge"


# ── Configuration ────────────────────────────────────────────────────────────


def configure_tracing(
    service_name: str = "labelforge",
    *,
    exporter: Optional[Any] = None,
    console: bool = False,
) -> Optional[Any]:
    """Install a TracerProvider on the global OTel API.

    - Honours ``OTEL_EXPORTER_OTLP_ENDPOINT`` / ``OTEL_EXPORTER_OTLP_HEADERS``
      env vars when ``exporter`` is not supplied.
    - Falls back to a no-op provider when OTel libs are absent.
    - Safe to call multiple times: re-entrant calls are a no-op.

    Returns the installed provider (``None`` when OTel unavailable).
    """
    global _CONFIGURED, _PROVIDER, _SERVICE_NAME

    if _CONFIGURED:
        return _PROVIDER
    _SERVICE_NAME = service_name

    if not OTEL_AVAILABLE:
        _CONFIGURED = True
        return None

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "labelforge",
            "service.version": os.getenv("LABELFORGE_VERSION", "0.1.0"),
            "deployment.environment": os.getenv("APP_ENV", "development"),
        }
    )
    provider = TracerProvider(resource=resource)

    # Exporter selection:
    #   - caller override wins
    #   - else if OTEL_EXPORTER_OTLP_ENDPOINT set → OTLP/HTTP
    #   - else if ``console`` or LABELFORGE_TRACE_CONSOLE=1 → ConsoleSpanExporter
    #   - else no span processor (tracing becomes a cheap no-op)
    picked = exporter
    if picked is None:
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                    OTLPSpanExporter,
                )

                picked = OTLPSpanExporter()  # reads endpoint+headers from env
            except Exception as exc:  # pragma: no cover
                _lazy_log().warning("tracing.otlp_exporter_failed", error=str(exc))

    if picked is None and (console or os.getenv("LABELFORGE_TRACE_CONSOLE", "") == "1"):
        picked = ConsoleSpanExporter()

    if picked is not None:
        # Prefer batch processor in real environments; simple processor in
        # console/test so spans flush inline and are deterministic.
        if isinstance(picked, ConsoleSpanExporter):
            provider.add_span_processor(SimpleSpanProcessor(picked))
        else:
            provider.add_span_processor(BatchSpanProcessor(picked))

    trace.set_tracer_provider(provider)
    _PROVIDER = provider
    _CONFIGURED = True
    return provider


def get_tracer(name: str) -> Any:
    """Return a tracer scoped to ``name``. Lazy-configures if needed."""
    if not _CONFIGURED:
        configure_tracing()
    if not OTEL_AVAILABLE:
        return _NoopTracer()
    return trace.get_tracer(name)


def get_trace_context() -> Tuple[Optional[str], Optional[str]]:
    """Return ``(trace_id_hex, span_id_hex)`` for the current span.

    Both are ``None`` when no span is active (or OTel unavailable).
    """
    if not OTEL_AVAILABLE:
        return (None, None)
    span = trace.get_current_span()
    if span is None:
        return (None, None)
    ctx = span.get_span_context()
    if not ctx or not ctx.is_valid:
        return (None, None)
    return (format(ctx.trace_id, "032x"), format(ctx.span_id, "016x"))


# ── Auto-instrumentation helpers ─────────────────────────────────────────────


def instrument_fastapi(app: Any) -> None:
    """Wire FastAPI request spans + propagation. Safe to call multiple times."""
    if not OTEL_AVAILABLE:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        # FastAPIInstrumentor is idempotent per-app.
        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:  # pragma: no cover — defensive
        _lazy_log().warning("tracing.fastapi_instrument_failed", error=str(exc))


def instrument_sqlalchemy(engine: Any) -> None:
    """Attach a span per SQLAlchemy query on ``engine``."""
    if not OTEL_AVAILABLE:
        return
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        # ``sync_engine`` covers both sync + async engines (the async engine
        # wraps a sync core internally).
        target = getattr(engine, "sync_engine", engine)
        SQLAlchemyInstrumentor().instrument(engine=target)
    except Exception as exc:  # pragma: no cover
        _lazy_log().warning("tracing.sqlalchemy_instrument_failed", error=str(exc))


def instrument_httpx() -> None:
    """Trace outbound httpx calls. Call once at startup."""
    if not OTEL_AVAILABLE:
        return
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception as exc:  # pragma: no cover
        _lazy_log().warning("tracing.httpx_instrument_failed", error=str(exc))


def instrument_logging() -> None:
    """Inject trace_id/span_id into stdlib log records (for non-structlog logs)."""
    if not OTEL_AVAILABLE:
        return
    try:
        from opentelemetry.instrumentation.logging import LoggingInstrumentor

        LoggingInstrumentor().instrument(set_logging_format=False)
    except Exception as exc:  # pragma: no cover
        _lazy_log().warning("tracing.logging_instrument_failed", error=str(exc))


# ── No-op fallbacks ──────────────────────────────────────────────────────────


class _NoopSpan:
    def set_attribute(self, *_: Any, **__: Any) -> None: ...
    def set_status(self, *_: Any, **__: Any) -> None: ...
    def record_exception(self, *_: Any, **__: Any) -> None: ...
    def add_event(self, *_: Any, **__: Any) -> None: ...
    def end(self) -> None: ...

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, *_: Any) -> None: ...


class _NoopTracer:
    def start_as_current_span(self, *_: Any, **__: Any) -> _NoopSpan:
        return _NoopSpan()

    def start_span(self, *_: Any, **__: Any) -> _NoopSpan:
        return _NoopSpan()


# ── Public re-exports ────────────────────────────────────────────────────────


def mark_error(span: Any, exc: BaseException) -> None:
    """Helper: record an exception on ``span`` and flip status to ERROR."""
    if not OTEL_AVAILABLE or span is None:
        return
    try:
        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, str(exc)))
    except Exception:  # pragma: no cover
        pass


__all__ = [
    "OTEL_AVAILABLE",
    "configure_tracing",
    "get_tracer",
    "get_trace_context",
    "instrument_fastapi",
    "instrument_sqlalchemy",
    "instrument_httpx",
    "instrument_logging",
    "mark_error",
]
