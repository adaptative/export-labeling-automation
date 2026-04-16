"""Integration tests for the /metrics and /health endpoints (Sprint-16)."""
from __future__ import annotations


class TestMetricsEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_metrics_endpoint_is_public(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_content_type(self, client):
        resp = client.get("/metrics")
        ct = resp.headers.get("content-type", "")
        # Both plain text and OpenMetrics flavours are acceptable.
        assert "text/plain" in ct or "openmetrics" in ct

    def test_metrics_includes_labelforge_metrics(self, client, admin_headers):
        # Generate some traffic first.
        client.get("/api/v1/ping", headers=admin_headers)
        resp = client.get("/metrics")
        body = resp.text
        # At least one of our metric families should appear.
        assert (
            "labelforge_requests_total" in body
            or "prometheus_client not installed" in body
        )
