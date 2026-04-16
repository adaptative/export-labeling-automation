"""Base agent interface with built-in tracing + metrics (TASK-040/041).

Every subclass of :class:`BaseAgent` automatically gets:

* an OTel span named ``agent.{agent_id}.execute`` covering each call
* Prometheus agent duration/success counters
* an entry in :mod:`labelforge.agents.registry` so the
  ``/api/v1/agents`` endpoint can surface live telemetry

The instrumentation is applied once via ``__init_subclass__`` — concrete
agents do not need to opt in or change their signatures.
"""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import wraps
from typing import Any, Optional

from labelforge.core.logging import bind_context, get_logger
from labelforge.core.metrics import record_agent_call, record_cost
from labelforge.core.tracing import get_tracer, mark_error


_log = get_logger("labelforge.agent")


@dataclass
class AgentResult:
    success: bool
    data: Any
    confidence: float = 1.0
    needs_hitl: bool = False
    hitl_reason: Optional[str] = None
    cost: float = 0.0


class BaseAgent(ABC):
    """All agents inherit from this class.

    Subclasses override :meth:`execute`; they do not need to wrap spans
    or metrics — the base class does it via ``__init_subclass__``.
    """

    agent_id: str = "unknown"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        raw = cls.__dict__.get("execute")
        if raw is None or getattr(raw, "__labelforge_instrumented__", False):
            return
        if not asyncio.iscoroutinefunction(raw):
            # Not expected (BaseAgent.execute is async) but stay permissive.
            return

        @wraps(raw)
        async def wrapper(self: "BaseAgent", input_data: dict, *args: Any, **kwargs: Any) -> AgentResult:
            from labelforge.agents.registry import record_agent_event

            agent_id = getattr(self, "agent_id", cls.__name__)
            tenant_id = None
            if isinstance(input_data, dict):
                tenant_id = input_data.get("tenant_id") or input_data.get("tenantId")
            bind_context(agent_id=agent_id)
            tracer = get_tracer("labelforge.agent")
            start = time.perf_counter()
            span_cm = tracer.start_as_current_span(f"agent.{agent_id}.execute")
            with span_cm as span:
                try:
                    try:
                        span.set_attribute("labelforge.agent_id", agent_id)
                        if tenant_id:
                            span.set_attribute("labelforge.tenant_id", tenant_id)
                    except Exception:
                        pass
                    result = await raw(self, input_data, *args, **kwargs)
                except Exception as exc:
                    duration = time.perf_counter() - start
                    record_agent_call(agent_id=agent_id, success=False, duration_seconds=duration)
                    record_agent_event(
                        agent_id=agent_id,
                        success=False,
                        duration_seconds=duration,
                        cost_usd=0.0,
                    )
                    mark_error(span, exc)
                    _log.exception(
                        "agent.execute.error",
                        agent_id=agent_id,
                        duration_ms=round(duration * 1000, 2),
                    )
                    raise
                else:
                    duration = time.perf_counter() - start
                    success = bool(getattr(result, "success", True))
                    cost_usd = float(getattr(result, "cost", 0.0) or 0.0)
                    record_agent_call(
                        agent_id=agent_id,
                        success=success,
                        duration_seconds=duration,
                    )
                    record_agent_event(
                        agent_id=agent_id,
                        success=success,
                        duration_seconds=duration,
                        cost_usd=cost_usd,
                    )
                    if cost_usd > 0 and tenant_id:
                        record_cost(tenant_id=tenant_id, scope="agent", amount_usd=cost_usd)
                    try:
                        span.set_attribute("labelforge.agent.success", success)
                        span.set_attribute("labelforge.agent.cost_usd", cost_usd)
                    except Exception:
                        pass
                    return result

        wrapper.__labelforge_instrumented__ = True  # type: ignore[attr-defined]
        cls.execute = wrapper  # type: ignore[assignment]

    @abstractmethod
    async def execute(self, input_data: dict) -> AgentResult:
        ...
