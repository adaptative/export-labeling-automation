"""Tests for budget / cost-breaker API endpoints."""
from __future__ import annotations

import pytest

PREFIX = "/api/v1/budgets"


# -- GET /budgets/current-spend -----------------------------------------------


class TestCurrentSpend:
    def test_returns_four_tiers(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/current-spend", headers=admin_headers)
        assert resp.status_code == 200
        tiers = resp.json()["tiers"]
        assert len(tiers) == 4

    def test_tier_ids(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/current-spend", headers=admin_headers)
        ids = {t["id"] for t in resp.json()["tiers"]}
        assert ids == {"llm_inference", "api_calls", "storage", "hitl"}

    def test_tier_has_required_fields(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/current-spend", headers=admin_headers)
        for tier in resp.json()["tiers"]:
            assert "id" in tier
            assert "name" in tier
            assert "current_spend" in tier
            assert "cap" in tier
            assert "unit" in tier
            assert "trend_pct" in tier
            assert "breaker_active" in tier

    def test_tier_values_are_numeric(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/current-spend", headers=admin_headers)
        for tier in resp.json()["tiers"]:
            assert isinstance(tier["current_spend"], (int, float))
            assert isinstance(tier["cap"], (int, float))
            assert isinstance(tier["trend_pct"], (int, float))


# -- GET /budgets/events ------------------------------------------------------


class TestBreakerEvents:
    def test_returns_events(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/events", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "total" in data
        assert len(data["events"]) > 0

    def test_event_structure(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/events", headers=admin_headers)
        event = resp.json()["events"][0]
        assert "id" in event
        assert "timestamp" in event
        assert "tier" in event
        assert "event_type" in event
        assert "triggered_by" in event
        assert "action" in event
        assert "status" in event

    def test_filter_by_tier(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/events", params={"tier": "llm_inference"}, headers=admin_headers)
        assert resp.status_code == 200
        for event in resp.json()["events"]:
            assert event["tier"] == "llm_inference"

    def test_filter_unknown_tier_returns_empty(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/events", params={"tier": "nonexistent"}, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["events"] == []
        assert resp.json()["total"] == 0

    def test_pagination_limit(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/events", params={"limit": 2}, headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["events"]) <= 2

    def test_pagination_offset(self, client, admin_headers):
        all_resp = client.get(f"{PREFIX}/events", headers=admin_headers)
        offset_resp = client.get(f"{PREFIX}/events", params={"offset": 2}, headers=admin_headers)
        all_events = all_resp.json()["events"]
        offset_events = offset_resp.json()["events"]
        if len(all_events) > 2:
            assert offset_events[0]["id"] == all_events[2]["id"]


# -- PUT /budgets/tenant/{id}/caps --------------------------------------------


class TestUpdateCaps:
    def test_update_valid_tier(self, client, admin_headers):
        resp = client.put(
            f"{PREFIX}/tenant/tnt-nakoda-001/caps",
            json={"tier": "llm_inference", "new_cap": 2000.0, "reason": "Increased for Q2"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"]["cap"] == 2000.0
        assert data["previous_cap"] == 1000.0
        assert data["reason"] == "Increased for Q2"

    def test_update_invalid_tier(self, client, admin_headers):
        resp = client.put(
            f"{PREFIX}/tenant/tnt-nakoda-001/caps",
            json={"tier": "invalid_tier", "new_cap": 100.0, "reason": "test"},
            headers=admin_headers,
        )
        assert resp.status_code in (400, 404)

    def test_update_negative_cap_rejected(self, client, admin_headers):
        resp = client.put(
            f"{PREFIX}/tenant/tnt-nakoda-001/caps",
            json={"tier": "llm_inference", "new_cap": -10.0, "reason": "test"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_update_zero_cap_rejected(self, client, admin_headers):
        resp = client.put(
            f"{PREFIX}/tenant/tnt-nakoda-001/caps",
            json={"tier": "llm_inference", "new_cap": 0, "reason": "test"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_update_empty_reason_rejected(self, client, admin_headers):
        resp = client.put(
            f"{PREFIX}/tenant/tnt-nakoda-001/caps",
            json={"tier": "llm_inference", "new_cap": 500.0, "reason": ""},
            headers=admin_headers,
        )
        assert resp.status_code == 422
