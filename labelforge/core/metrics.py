"""Prometheus metrics registry and /metrics endpoint (TASK-041).

All metrics for labelforge live here. The module is self-contained:
importing it does not require ``prometheus_client``. When the lib is
absent (minimal test envs), every metric is swapped for a no-op so
call-sites stay one-liners.

Metrics taxonomy
----------------

Histograms:
  ``labelforge_request_duration_seconds``  labels: method, path, status
  ``labelforge_agent_duration_seconds``    labels: agent_id, success

Counters:
  ``labelforge_requests_total``            labels: method, path, status
  ``labelforge_agent_calls_total``         labels: agent_id, success
  ``labelforge_cost_usd_total``            labels: tenant_id, scope
  ``labelforge_errors_total``              labels: category

Gauges:
  ``labelforge_hitl_queue_depth``          labels: tenant_id, status
  ``labelforge_automation_rate``           labels: tenant_id

Public surface
--------------

* ``get_registry()``            – the shared CollectorRegistry
* ``record_request(...)``       – observe latency/total/errors in one call
* ``record_agent_call(...)``    – observe agent execute() outcome
* ``record_cost(...)``          – bump cost counter
* ``observe_queue_depth(...)``  – set gauge
* ``set_automation_rate(...)``  – set gauge
* ``render_metrics()``          – return (payload bytes, content-type)
* ``PrometheusMiddleware``      – ASGI middleware for req histograms
"""
from __future__ import annotations

import time
from typing import Any, MutableMapping, Optional, Tuple

try:
    from prometheus_client import (  # type: ignore
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except Exception:  # pragma: no cover — only hit in stripped envs
    CONTENT_TYPE_LATEST = "text/plain; charset=utf-8"
    CollectorRegistry = None  # type: ignore[assignment]
    Counter = None  # type: ignore[assignment]
    Gauge = None  # type: ignore[assignment]
    Histogram = None  # type: ignore[assignment]
    generate_latest = None  # type: ignore[assignment]
    PROMETHEUS_AVAILABLE = False


# Latency buckets tuned for typical API/agent calls (5 ms → 30 s).
_REQUEST_BUCKETS = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0,
)


# ── Registry + metric construction ───────────────────────────────────────────

class _NoopMetric:
    """Stand-in when prometheus_client is missing."""

    def labels(self, *_: Any, **__: Any) -> "_NoopMetric":
        return self

    def observe(self, *_: Any, **__: Any) -> None: ...
    def inc(self, *_: Any, **__: Any) -> None: ...
    def set(self, *_: Any, **__: Any) -> None: ...


def _build_registry() -> Tuple[Any, MutableMapping[str, Any]]:
    if not PROMETHEUS_AVAILABLE:
        noop = _NoopMetric()
        return None, {
            "request_duration": noop,
            "agent_duration": noop,
            "requests_total": noop,
            "agent_calls_total": noop,
            "cost_usd_total": noop,
            "errors_total": noop,
            "hitl_queue_depth": noop,
            "automation_rate": noop,
        }

    registry = CollectorRegistry()
    metrics = {
        "request_duration": Histogram(
            "labelforge_request_duration_seconds",
            "HTTP request latency in seconds.",
            ["method", "path", "status"],
            buckets=_REQUEST_BUCKETS,
            registry=registry,
        ),
        "agent_duration": Histogram(
            "labelforge_agent_duration_seconds",
            "Agent execute() latency in seconds.",
            ["agent_id", "success"],
            buckets=_REQUEST_BUCKETS,
            registry=registry,
        ),
        "requests_total": Counter(
            "labelforge_requests_total",
            "Total HTTP requests.",
            ["method", "path", "status"],
            registry=registry,
        ),
        "agent_calls_total": Counter(
            "labelforge_agent_calls_total",
            "Total agent invocations.",
            ["agent_id", "success"],
            registry=registry,
        ),
        "cost_usd_total": Counter(
            "labelforge_cost_usd_total",
            "Accumulated USD cost across all agents/providers.",
            ["tenant_id", "scope"],
            registry=registry,
        ),
        "errors_total": Counter(
            "labelforge_errors_total",
            "Total categorized errors (500s, agent failures, transports).",
            ["category"],
            registry=registry,
        ),
        "hitl_queue_depth": Gauge(
            "labelforge_hitl_queue_depth",
            "Current HiTL queue depth by status.",
            ["tenant_id", "status"],
            registry=registry,
        ),
        "automation_rate": Gauge(
            "labelforge_automation_rate",
            "Latest automation rate as a percentage (0-100).",
            ["tenant_id"],
            registry=registry,
        ),
    }
    return registry, metrics


_REGISTRY, _METRICS = _build_registry()


def get_registry() -> Any:
    """Return the shared collector registry (``None`` if prometheus absent)."""
    return _REGISTRY


def metric(name: str) -> Any:
    """Fetch a metric object by logical name (``request_duration`` etc.)."""
    return _METRICS[name]


# ── Recording helpers ────────────────────────────────────────────────────────


def _normalize_path(path: str) -> str:
    """Avoid label cardinality explosion by collapsing id-like path segments.

    Any segment that looks like a UUID/hex/numeric/opaque id is replaced
    with ``:id``. The template ``/api/v1/orders/abc123`` becomes
    ``/api/v1/orders/:id``.
    """
    parts = path.split("/")
    out = []
    for seg in parts:
        if not seg:
            out.append(seg)
            continue
        # Heuristic: >= 10 chars and contains a digit => id.
        if len(seg) >= 10 and any(c.isdigit() for c in seg):
            out.append(":id")
        elif seg.replace("-", "").isdigit():
            out.append(":id")
        else:
            out.append(seg)
    return "/".join(out) or "/"


def record_request(*, method: str, path: str, status: int, duration_seconds: float) -> None:
    """Record the outcome of one HTTP request."""
    path = _normalize_path(path)
    status_str = str(status)
    _METRICS["request_duration"].labels(method=method, path=path, status=status_str).observe(
        max(0.0, duration_seconds)
    )
    _METRICS["requests_total"].labels(method=method, path=path, status=status_str).inc()
    if status >= 500:
        _METRICS["errors_total"].labels(category="http_5xx").inc()


def record_agent_call(*, agent_id: str, success: bool, duration_seconds: float) -> None:
    """Record the outcome of one agent ``execute`` call."""
    success_str = "true" if success else "false"
    _METRICS["agent_duration"].labels(agent_id=agent_id, success=success_str).observe(
        max(0.0, duration_seconds)
    )
    _METRICS["agent_calls_total"].labels(agent_id=agent_id, success=success_str).inc()
    if not success:
        _METRICS["errors_total"].labels(category="agent_failure").inc()


def record_cost(*, tenant_id: str, scope: str, amount_usd: float) -> None:
    """Bump the cumulative USD cost counter."""
    if amount_usd <= 0:
        return
    _METRICS["cost_usd_total"].labels(tenant_id=tenant_id or "unknown", scope=scope).inc(
        amount_usd
    )


def record_error(category: str) -> None:
    """Categorised error counter (``transport_transient``, ``budget_exceeded`` …)."""
    _METRICS["errors_total"].labels(category=category).inc()


def observe_queue_depth(*, tenant_id: str, status: str, depth: int) -> None:
    _METRICS["hitl_queue_depth"].labels(tenant_id=tenant_id or "unknown", status=status).set(
        float(depth)
    )


def set_automation_rate(*, tenant_id: str, rate_percent: float) -> None:
    _METRICS["automation_rate"].labels(tenant_id=tenant_id or "unknown").set(
        float(rate_percent)
    )


def render_metrics() -> Tuple[bytes, str]:
    """Return (payload bytes, content-type) for the ``/metrics`` endpoint."""
    if not PROMETHEUS_AVAILABLE or _REGISTRY is None:
        return (b"# prometheus_client not installed\n", CONTENT_TYPE_LATEST)
    return (generate_latest(_REGISTRY), CONTENT_TYPE_LATEST)


# ── ASGI middleware ──────────────────────────────────────────────────────────


class PrometheusMiddleware:
    """ASGI middleware that records request duration + status codes."""

    EXCLUDE_PATHS = {"/metrics", "/health"}

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self.EXCLUDE_PATHS:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        start = time.perf_counter()
        status_holder: dict[str, int] = {}

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = int(message.get("status", 0))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration = time.perf_counter() - start
            record_request(method=method, path=path, status=500, duration_seconds=duration)
            raise
        else:
            duration = time.perf_counter() - start
            status = status_holder.get("status", 0)
            record_request(method=method, path=path, status=status, duration_seconds=duration)


__all__ = [
    "PROMETHEUS_AVAILABLE",
    "PrometheusMiddleware",
    "get_registry",
    "metric",
    "record_agent_call",
    "record_cost",
    "record_error",
    "record_request",
    "render_metrics",
    "observe_queue_depth",
    "set_automation_rate",
]
