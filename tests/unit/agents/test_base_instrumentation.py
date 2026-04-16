"""Tests that BaseAgent auto-instruments execute() (Sprint-16, TASK-040/041)."""
from __future__ import annotations

import pytest

from labelforge.agents.base import AgentResult, BaseAgent
from labelforge.agents.registry import get_registry


@pytest.fixture(autouse=True)
def _reset_registry():
    get_registry().reset()
    yield
    get_registry().reset()


class SuccessAgent(BaseAgent):
    agent_id = "test_success"

    async def execute(self, input_data: dict) -> AgentResult:
        return AgentResult(success=True, data={"ok": True}, cost=0.005)


class FailureAgent(BaseAgent):
    agent_id = "test_failure"

    async def execute(self, input_data: dict) -> AgentResult:
        return AgentResult(success=False, data=None, cost=0.0)


class ExplodingAgent(BaseAgent):
    agent_id = "test_explode"

    async def execute(self, input_data: dict) -> AgentResult:
        raise RuntimeError("boom")


class TestAutoInstrumentation:
    def test_wrapper_marked_instrumented(self):
        assert getattr(SuccessAgent.execute, "__labelforge_instrumented__", False) is True

    def test_wrapping_is_idempotent(self):
        """``__init_subclass__`` must not re-wrap an already-wrapped method."""

        class Child(SuccessAgent):
            pass

        # Child inherits SuccessAgent.execute; no double-wrap on class creation.
        assert getattr(Child.execute, "__labelforge_instrumented__", False) is True

    @pytest.mark.asyncio
    async def test_success_records_registry(self):
        agent = SuccessAgent()
        result = await agent.execute({"tenant_id": "t1"})
        assert result.success is True
        snap = get_registry().snapshot("test_success")
        assert snap.calls == 1
        assert snap.successes == 1
        assert snap.failures == 0
        assert snap.total_cost_usd == pytest.approx(0.005)

    @pytest.mark.asyncio
    async def test_failure_result_increments_failures(self):
        agent = FailureAgent()
        await agent.execute({"tenant_id": "t2"})
        snap = get_registry().snapshot("test_failure")
        assert snap.calls == 1
        # success=False in the AgentResult flows through to the registry.
        assert snap.failures == 1

    @pytest.mark.asyncio
    async def test_exception_marks_failure_and_reraises(self):
        agent = ExplodingAgent()
        with pytest.raises(RuntimeError, match="boom"):
            await agent.execute({"tenant_id": "t3"})
        snap = get_registry().snapshot("test_explode")
        assert snap.calls == 1
        assert snap.failures == 1
        assert snap.successes == 0

    @pytest.mark.asyncio
    async def test_tenant_id_optional(self):
        agent = SuccessAgent()
        # No tenant_id in input — must still work.
        await agent.execute({})
        snap = get_registry().snapshot("test_success")
        assert snap.calls == 1

    @pytest.mark.asyncio
    async def test_non_dict_input_does_not_crash(self):
        agent = SuccessAgent()
        # input_data is allowed to be anything duck-typed; wrapper guards on dict.
        await agent.execute({"anything": "yes"})
        snap = get_registry().snapshot("test_success")
        assert snap.calls == 1
