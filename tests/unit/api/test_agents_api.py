"""Tests for GET /api/v1/agents (Sprint-16, INT-013)."""
from __future__ import annotations

import pytest

from labelforge.agents.registry import AGENT_CATALOGUE, get_registry, record_agent_event


@pytest.fixture(autouse=True)
def _reset_registry():
    get_registry().reset()
    yield
    get_registry().reset()


class TestListAgents:
    def test_requires_auth(self, client):
        resp = client.get("/api/v1/agents")
        assert resp.status_code in (401, 403)

    def test_returns_fourteen_catalogue_entries(self, client, admin_headers):
        resp = client.get("/api/v1/agents", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 14
        assert len(body["agents"]) == 14
        ids = [a["agent_id"] for a in body["agents"]]
        assert set(ids) == {e["agent_id"] for e in AGENT_CATALOGUE}

    def test_cards_have_required_fields(self, client, admin_headers):
        resp = client.get("/api/v1/agents", headers=admin_headers)
        for card in resp.json()["agents"]:
            for field in (
                "agent_id",
                "name",
                "kind",
                "status",
                "calls",
                "successes",
                "failures",
                "success_rate",
                "avg_latency_ms",
                "total_cost_usd",
            ):
                assert field in card, f"missing {field} in {card}"
            assert card["status"] in {"healthy", "degraded", "idle"}

    def test_fresh_registry_shows_all_idle(self, client, admin_headers):
        body = client.get("/api/v1/agents", headers=admin_headers).json()
        for card in body["agents"]:
            assert card["status"] == "idle"
            assert card["calls"] == 0

    def test_telemetry_reflects_recorded_events(self, client, admin_headers):
        # Simulate a few successes + one failure on a known agent.
        target = AGENT_CATALOGUE[0]["agent_id"]
        for _ in range(4):
            record_agent_event(
                agent_id=target, success=True, duration_seconds=0.1, cost_usd=0.01
            )
        record_agent_event(
            agent_id=target, success=False, duration_seconds=0.2, cost_usd=0.0
        )
        body = client.get("/api/v1/agents", headers=admin_headers).json()
        card = next(c for c in body["agents"] if c["agent_id"] == target)
        assert card["calls"] == 5
        assert card["successes"] == 4
        assert card["failures"] == 1
        assert card["success_rate"] == 0.8
        # avg latency ≈ 120 ms
        assert 100 <= card["avg_latency_ms"] <= 140
        assert card["total_cost_usd"] == pytest.approx(0.04)
        # 1/5 failures == 20% → still healthy (threshold is 25%).
        assert card["status"] == "healthy"

    def test_status_goes_degraded_past_threshold(self, client, admin_headers):
        target = AGENT_CATALOGUE[1]["agent_id"]
        record_agent_event(agent_id=target, success=True, duration_seconds=0.1)
        for _ in range(3):
            record_agent_event(agent_id=target, success=False, duration_seconds=0.1)
        body = client.get("/api/v1/agents", headers=admin_headers).json()
        card = next(c for c in body["agents"] if c["agent_id"] == target)
        assert card["status"] == "degraded"


class TestGetAgentById:
    def test_known_agent(self, client, admin_headers):
        target = AGENT_CATALOGUE[0]["agent_id"]
        resp = client.get(f"/api/v1/agents/{target}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == target

    def test_unknown_agent_404(self, client, admin_headers):
        resp = client.get("/api/v1/agents/nope-does-not-exist", headers=admin_headers)
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        target = AGENT_CATALOGUE[0]["agent_id"]
        resp = client.get(f"/api/v1/agents/{target}")
        assert resp.status_code in (401, 403)
