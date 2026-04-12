"""Tests for worker lifecycle and activity registration."""
from __future__ import annotations

import pytest

from labelforge.core.worker import (
    ActivityRegistration,
    Worker,
    WorkerHealth,
    WorkerState,
)


class TestWorkerState:
    def test_all_states(self):
        states = [s.value for s in WorkerState]
        assert "idle" in states
        assert "starting" in states
        assert "running" in states
        assert "draining" in states
        assert "stopped" in states


class TestWorker:
    def test_initial_state_is_idle(self):
        w = Worker()
        assert w.state == WorkerState.IDLE

    def test_task_queue(self):
        w = Worker(task_queue="my-queue")
        assert w.task_queue == "my-queue"

    @pytest.mark.asyncio
    async def test_start(self):
        w = Worker()
        await w.start()
        assert w.state == WorkerState.RUNNING

    @pytest.mark.asyncio
    async def test_start_twice_raises(self):
        w = Worker()
        await w.start()
        with pytest.raises(RuntimeError):
            await w.start()

    @pytest.mark.asyncio
    async def test_graceful_stop(self):
        w = Worker()
        await w.start()
        await w.stop(graceful=True)
        assert w.state == WorkerState.STOPPED

    @pytest.mark.asyncio
    async def test_force_stop(self):
        w = Worker()
        await w.start()
        await w.stop(graceful=False)
        assert w.state == WorkerState.STOPPED

    @pytest.mark.asyncio
    async def test_stop_idempotent(self):
        w = Worker()
        await w.start()
        await w.stop()
        await w.stop()  # Should not raise
        assert w.state == WorkerState.STOPPED


class TestActivityRegistration:
    def test_register_activity(self):
        w = Worker()
        reg = w.register_activity("extract_text", "extractor-agent")
        assert reg.name == "extract_text"
        assert reg.agent_id == "extractor-agent"
        assert reg.registered_at > 0

    def test_register_multiple_activities(self):
        w = Worker()
        w.register_activity("act1", "agent-a")
        w.register_activity("act2", "agent-b")
        w.register_activity("act3", "agent-a")
        assert len(w.get_activities()) == 3

    def test_filter_by_agent(self):
        w = Worker()
        w.register_activity("act1", "agent-a")
        w.register_activity("act2", "agent-b")
        w.register_activity("act3", "agent-a")
        a_acts = w.get_activities(agent_id="agent-a")
        assert len(a_acts) == 2
        assert all(a.agent_id == "agent-a" for a in a_acts)

    @pytest.mark.asyncio
    async def test_register_while_running(self):
        w = Worker()
        await w.start()
        reg = w.register_activity("runtime_act", "agent-x")
        assert reg.name == "runtime_act"

    @pytest.mark.asyncio
    async def test_register_after_stop_raises(self):
        w = Worker()
        await w.start()
        await w.stop()
        with pytest.raises(RuntimeError):
            w.register_activity("late_act", "agent-y")

    def test_register_with_handler(self):
        def my_handler():
            pass
        w = Worker()
        reg = w.register_activity("act", "agent", handler=my_handler)
        assert reg.handler is my_handler


class TestWorkerHealth:
    def test_health_idle(self):
        w = Worker()
        h = w.health()
        assert h.state == WorkerState.IDLE
        assert h.activities_registered == 0
        assert h.active_tasks == 0

    @pytest.mark.asyncio
    async def test_health_running(self):
        w = Worker()
        w.register_activity("act1", "agent-a")
        await w.start()
        h = w.health()
        assert h.state == WorkerState.RUNNING
        assert h.activities_registered == 1
        assert h.uptime_seconds >= 0

    def test_heartbeat_updates_timestamp(self):
        w = Worker()
        old_hb = w.health().last_heartbeat
        w.heartbeat()
        new_hb = w.health().last_heartbeat
        assert new_hb >= old_hb

    @pytest.mark.asyncio
    async def test_health_after_stop(self):
        w = Worker()
        await w.start()
        await w.stop()
        h = w.health()
        assert h.state == WorkerState.STOPPED
