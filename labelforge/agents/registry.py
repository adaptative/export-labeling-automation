"""In-memory agent telemetry registry (INT-013 backend support).

Every instrumented :class:`labelforge.agents.base.BaseAgent.execute`
call funnels through :func:`record_agent_event`, which keeps
process-local running totals per agent_id. The ``/api/v1/agents``
endpoint reads from this registry.

This is intentionally *process-local*: Prometheus is the durable
cross-replica truth. The registry exists purely so the web UI can show
a friendly card grid without scraping Prometheus.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# Canonical list of the 14 agents surfaced in the UI (see #102).
# "kind" is a broad taxonomy used for grouping in the frontend.
AGENT_CATALOGUE: List[Dict[str, str]] = [
    {"agent_id": "protocol_analyzer", "name": "Protocol Analyzer", "kind": "intake"},
    {"agent_id": "intake_classifier", "name": "Intake Classifier", "kind": "intake"},
    {"agent_id": "provenance_tracker", "name": "Provenance Tracker", "kind": "intake"},
    {"agent_id": "order_processor", "name": "Order Processor", "kind": "orchestration"},
    {"agent_id": "fusion_agent", "name": "Fusion Agent", "kind": "fusion"},
    {"agent_id": "compliance_classifier", "name": "Compliance Classifier", "kind": "compliance"},
    {"agent_id": "composer_agent", "name": "Composer Agent", "kind": "composition"},
    {"agent_id": "validator_agent", "name": "Validator Agent", "kind": "composition"},
    {"agent_id": "hitl_resolver", "name": "HiTL Resolver", "kind": "hitl"},
    {"agent_id": "rule_evaluator", "name": "Rule Evaluator", "kind": "compliance"},
    {"agent_id": "cost_breaker", "name": "Cost Breaker", "kind": "guardrail"},
    {"agent_id": "artifact_generator", "name": "Artifact Generator", "kind": "output"},
    {"agent_id": "bundle_assembler", "name": "Bundle Assembler", "kind": "output"},
    {"agent_id": "notification_dispatcher", "name": "Notification Dispatcher", "kind": "notification"},
]


@dataclass
class AgentTelemetry:
    agent_id: str
    calls: int = 0
    successes: int = 0
    failures: int = 0
    total_duration_s: float = 0.0
    total_cost_usd: float = 0.0
    last_call_at: Optional[float] = None  # unix-seconds


@dataclass
class AgentRegistry:
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _by_id: Dict[str, AgentTelemetry] = field(default_factory=dict)

    def record(
        self,
        *,
        agent_id: str,
        success: bool,
        duration_seconds: float,
        cost_usd: float = 0.0,
    ) -> None:
        with self._lock:
            entry = self._by_id.get(agent_id)
            if entry is None:
                entry = AgentTelemetry(agent_id=agent_id)
                self._by_id[agent_id] = entry
            entry.calls += 1
            if success:
                entry.successes += 1
            else:
                entry.failures += 1
            entry.total_duration_s += max(0.0, duration_seconds)
            entry.total_cost_usd += max(0.0, cost_usd)
            entry.last_call_at = time.time()

    def snapshot(self, agent_id: str) -> AgentTelemetry:
        with self._lock:
            entry = self._by_id.get(agent_id)
            if entry is None:
                return AgentTelemetry(agent_id=agent_id)
            return AgentTelemetry(
                agent_id=entry.agent_id,
                calls=entry.calls,
                successes=entry.successes,
                failures=entry.failures,
                total_duration_s=entry.total_duration_s,
                total_cost_usd=entry.total_cost_usd,
                last_call_at=entry.last_call_at,
            )

    def reset(self) -> None:
        with self._lock:
            self._by_id.clear()


_REGISTRY = AgentRegistry()


def get_registry() -> AgentRegistry:
    return _REGISTRY


def record_agent_event(
    *,
    agent_id: str,
    success: bool,
    duration_seconds: float,
    cost_usd: float = 0.0,
) -> None:
    """Wrapper used by :class:`BaseAgent` instrumentation."""
    _REGISTRY.record(
        agent_id=agent_id,
        success=success,
        duration_seconds=duration_seconds,
        cost_usd=cost_usd,
    )


__all__ = [
    "AGENT_CATALOGUE",
    "AgentRegistry",
    "AgentTelemetry",
    "get_registry",
    "record_agent_event",
]
