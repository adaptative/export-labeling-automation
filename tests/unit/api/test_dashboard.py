"""Tests for dashboard stats endpoint."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from labelforge.app import app


class TestDashboardStats:
    """Tests for GET /api/v1/dashboard/stats."""

    def test_returns_200_with_auth(self, client, admin_headers):
        resp = client.get("/api/v1/dashboard/stats", headers=admin_headers)
        assert resp.status_code == 200

    def test_returns_401_without_auth(self, client):
        resp = client.get("/api/v1/dashboard/stats")
        assert resp.status_code in (401, 403)

    def test_response_has_kpis(self, client, admin_headers):
        resp = client.get("/api/v1/dashboard/stats", headers=admin_headers)
        data = resp.json()
        assert "kpis" in data
        assert len(data["kpis"]) == 4

    def test_kpi_keys(self, client, admin_headers):
        resp = client.get("/api/v1/dashboard/stats", headers=admin_headers)
        kpis = resp.json()["kpis"]
        keys = {k["key"] for k in kpis}
        assert keys == {"active_orders", "hitl_open", "automation_rate", "today_spend"}

    def test_kpi_has_required_fields(self, client, admin_headers):
        resp = client.get("/api/v1/dashboard/stats", headers=admin_headers)
        for kpi in resp.json()["kpis"]:
            assert "key" in kpi
            assert "label" in kpi
            assert "value" in kpi
            assert "detail" in kpi

    def test_response_has_active_orders(self, client, admin_headers):
        resp = client.get("/api/v1/dashboard/stats", headers=admin_headers)
        data = resp.json()
        assert "active_orders" in data
        assert isinstance(data["active_orders"], list)

    def test_active_order_has_required_fields(self, client, admin_headers):
        resp = client.get("/api/v1/dashboard/stats", headers=admin_headers)
        for order in resp.json()["active_orders"]:
            assert "id" in order
            assert "po_number" in order
            assert "state" in order
            assert "progress" in order

    def test_response_has_recent_activity(self, client, admin_headers):
        resp = client.get("/api/v1/dashboard/stats", headers=admin_headers)
        data = resp.json()
        assert "recent_activity" in data
        assert isinstance(data["recent_activity"], list)

    def test_activity_entry_has_required_fields(self, client, admin_headers):
        resp = client.get("/api/v1/dashboard/stats", headers=admin_headers)
        for entry in resp.json()["recent_activity"]:
            assert "id" in entry
            assert "timestamp" in entry
            assert "actor" in entry
            assert "actor_type" in entry
            assert "detail" in entry

    def test_response_has_automation_series(self, client, admin_headers):
        resp = client.get("/api/v1/dashboard/stats", headers=admin_headers)
        data = resp.json()
        assert "automation_series" in data
        assert len(data["automation_series"]) > 0
        for point in data["automation_series"]:
            assert "date" in point
            assert "rate" in point

    def test_automation_rate_kpi_value_is_numeric(self, client, admin_headers):
        resp = client.get("/api/v1/dashboard/stats", headers=admin_headers)
        kpis = resp.json()["kpis"]
        rate_kpi = next(k for k in kpis if k["key"] == "automation_rate")
        assert isinstance(rate_kpi["value"], (int, float))
        assert 0 <= rate_kpi["value"] <= 100

    def test_today_spend_kpi_value_is_numeric(self, client, admin_headers):
        resp = client.get("/api/v1/dashboard/stats", headers=admin_headers)
        kpis = resp.json()["kpis"]
        spend_kpi = next(k for k in kpis if k["key"] == "today_spend")
        assert isinstance(spend_kpi["value"], (int, float))
        assert spend_kpi["value"] >= 0
