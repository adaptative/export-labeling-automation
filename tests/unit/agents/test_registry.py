"""Tests for labelforge.agents.registry (Sprint-16, INT-013)."""
from __future__ import annotations

import threading

import pytest

from labelforge.agents.registry import (
    AGENT_CATALOGUE,
    AgentRegistry,
    AgentTelemetry,
    get_registry,
    record_agent_event,
)


# ── Catalogue sanity ────────────────────────────────────────────────────────


class TestAgentCatalogue:
    def test_has_fourteen_agents(self):
        assert len(AGENT_CATALOGUE) == 14

    def test_every_entry_has_required_keys(self):
        for entry in AGENT_CATALOGUE:
            assert {"agent_id", "name", "kind"} <= set(entry.keys())

    def test_agent_ids_unique(self):
        ids = [e["agent_id"] for e in AGENT_CATALOGUE]
        assert len(ids) == len(set(ids))


# ── AgentRegistry ───────────────────────────────────────────────────────────


class TestAgentRegistry:
    def test_snapshot_unknown_agent_returns_empty(self):
        r = AgentRegistry()
        snap = r.snapshot("unknown")
        assert snap.agent_id == "unknown"
        assert snap.calls == 0
        assert snap.successes == 0
        assert snap.failures == 0
        assert snap.total_duration_s == 0.0
        assert snap.last_call_at is None

    def test_record_success(self):
        r = AgentRegistry()
        r.record(agent_id="a", success=True, duration_seconds=0.25, cost_usd=0.01)
        snap = r.snapshot("a")
        assert snap.calls == 1
        assert snap.successes == 1
        assert snap.failures == 0
        assert snap.total_duration_s == pytest.approx(0.25)
        assert snap.total_cost_usd == pytest.approx(0.01)
        assert snap.last_call_at is not None

    def test_record_failure(self):
        r = AgentRegistry()
        r.record(agent_id="a", success=False, duration_seconds=0.1)
        snap = r.snapshot("a")
        assert snap.failures == 1
        assert snap.successes == 0

    def test_record_accumulates(self):
        r = AgentRegistry()
        for i in range(5):
            r.record(
                agent_id="x",
                success=(i % 2 == 0),
                duration_seconds=0.1,
                cost_usd=0.02,
            )
        snap = r.snapshot("x")
        assert snap.calls == 5
        assert snap.successes == 3
        assert snap.failures == 2
        assert snap.total_duration_s == pytest.approx(0.5)
        assert snap.total_cost_usd == pytest.approx(0.1)

    def test_snapshot_returns_copy_not_reference(self):
        r = AgentRegistry()
        r.record(agent_id="b", success=True, duration_seconds=0.1)
        snap = r.snapshot("b")
        snap.calls = 999  # mutate the returned object
        # Original registry state should be unchanged.
        again = r.snapshot("b")
        assert again.calls == 1

    def test_negative_values_clamped(self):
        r = AgentRegistry()
        r.record(agent_id="neg", success=True, duration_seconds=-1, cost_usd=-2)
        snap = r.snapshot("neg")
        assert snap.total_duration_s == 0.0
        assert snap.total_cost_usd == 0.0

    def test_reset_clears_state(self):
        r = AgentRegistry()
        r.record(agent_id="a", success=True, duration_seconds=0.1)
        r.reset()
        snap = r.snapshot("a")
        assert snap.calls == 0


# ── thread-safety ───────────────────────────────────────────────────────────


class TestThreadSafety:
    def test_concurrent_recording(self):
        r = AgentRegistry()
        n_threads = 8
        n_iters = 200

        def worker():
            for _ in range(n_iters):
                r.record(agent_id="shared", success=True, duration_seconds=0.001)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        snap = r.snapshot("shared")
        assert snap.calls == n_threads * n_iters
        assert snap.successes == n_threads * n_iters


# ── module-level singleton ──────────────────────────────────────────────────


class TestModuleSingleton:
    def test_get_registry_returns_same_instance(self):
        assert get_registry() is get_registry()

    def test_record_agent_event_writes_to_singleton(self):
        before = get_registry().snapshot("singleton-test").calls
        record_agent_event(
            agent_id="singleton-test", success=True, duration_seconds=0.01, cost_usd=0
        )
        after = get_registry().snapshot("singleton-test").calls
        assert after == before + 1
        get_registry().reset()
