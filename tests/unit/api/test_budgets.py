"""Tests for budget / cost-breaker API endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from labelforge.api.v1.auth import _make_stub_jwt
from labelforge.app import app

client = TestClient(app)
PREFIX = "/api/v1/budgets"

_TOKEN = _make_stub_jwt("usr-admin-001", "tnt-nakoda-001", "ADMIN", "admin@nakodacraft.com")
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


# ── GET /budgets/current-spend ─────────────────────────────────────────────


class TestCurrentSpend:
    def test_returns_four_tiers(self):
        resp = client.get(f"{PREFIX}/current-spend", headers=_AUTH)
        assert resp.status_code == 200
        tiers = resp.json()["tiers"]
        assert len(tiers) == 4

    def test_tier_ids(self):
        resp = client.get(f"{PREFIX}/current-spend", headers=_AUTH)
        ids = {t["id"] for t in resp.json()["tiers"]}
        assert ids == {"llm_inference", "api_calls", "storage", "hitl"}

    def test_tier_has_required_fields(self):
        resp = client.get(f"{PREFIX}/current-spend", headers=_AUTH)
        for tier in resp.json()["tiers"]:
            assert "id" in tier
            assert "name" in tier
            assert "current_spend" in tier
            assert "cap" in tier
            assert "unit" in tier
            assert "trend_pct" in tier
            assert "breaker_active" in tier

    def test_tier_values_are_numeric(self):
        resp = client.get(f"{PREFIX}/current-spend", headers=_AUTH)
        for tier in resp.json()["tiers"]:
            assert isinstance(tier["current_spend"], (int, float))
            assert isinstance(tier["cap"], (int, float))
            assert isinstance(tier["trend_pct"], (int, float))


# ── GET /budgets/events ────────────────────────────────────────────────────


class TestBreakerEvents:
    def test_returns_events(self):
        resp = client.get(f"{PREFIX}/events", headers=_AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "total" in data
        assert len(data["events"]) > 0

    def test_event_structure(self):
        resp = client.get(f"{PREFIX}/events", headers=_AUTH)
        event = resp.json()["events"][0]
        assert "id" in event
        assert "timestamp" in event
        assert "tier" in event
        assert "event_type" in event
        assert "triggered_by" in event
        assert "action" in event
        assert "status" in event

    def test_filter_by_tier(self):
        resp = client.get(f"{PREFIX}/events", params={"tier": "llm_inference"}, headers=_AUTH)
        assert resp.status_code == 200
        for event in resp.json()["events"]:
            assert event["tier"] == "llm_inference"

    def test_filter_unknown_tier_returns_empty(self):
        resp = client.get(f"{PREFIX}/events", params={"tier": "nonexistent"}, headers=_AUTH)
        assert resp.status_code == 200
        assert resp.json()["events"] == []
        assert resp.json()["total"] == 0

    def test_pagination_limit(self):
        resp = client.get(f"{PREFIX}/events", params={"limit": 2}, headers=_AUTH)
        assert resp.status_code == 200
        assert len(resp.json()["events"]) <= 2

    def test_pagination_offset(self):
        all_resp = client.get(f"{PREFIX}/events", headers=_AUTH)
        offset_resp = client.get(f"{PREFIX}/events", params={"offset": 2}, headers=_AUTH)
        all_events = all_resp.json()["events"]
        offset_events = offset_resp.json()["events"]
        if len(all_events) > 2:
            assert offset_events[0]["id"] == all_events[2]["id"]


# ── PUT /budgets/tenant/{id}/caps ──────────────────────────────────────────


class TestUpdateCaps:
    def test_update_valid_tier(self):
        resp = client.put(
            f"{PREFIX}/tenant/tnt-001/caps",
            json={"tier": "llm_inference", "new_cap": 2000.0, "reason": "Increased for Q2"},
            headers=_AUTH,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"]["cap"] == 2000.0
        assert data["previous_cap"] == 1000.0
        assert data["reason"] == "Increased for Q2"

    def test_update_invalid_tier(self):
        resp = client.put(
            f"{PREFIX}/tenant/tnt-001/caps",
            json={"tier": "invalid_tier", "new_cap": 100.0, "reason": "test"},
            headers=_AUTH,
        )
        assert resp.status_code == 400

    def test_update_negative_cap_rejected(self):
        resp = client.put(
            f"{PREFIX}/tenant/tnt-001/caps",
            json={"tier": "llm_inference", "new_cap": -10.0, "reason": "test"},
            headers=_AUTH,
        )
        assert resp.status_code == 422

    def test_update_zero_cap_rejected(self):
        resp = client.put(
            f"{PREFIX}/tenant/tnt-001/caps",
            json={"tier": "llm_inference", "new_cap": 0, "reason": "test"},
            headers=_AUTH,
        )
        assert resp.status_code == 422

    def test_update_empty_reason_rejected(self):
        resp = client.put(
            f"{PREFIX}/tenant/tnt-001/caps",
            json={"tier": "llm_inference", "new_cap": 500.0, "reason": ""},
            headers=_AUTH,
        )
        assert resp.status_code == 422
