"""Worker lifecycle and activity registration.

Temporal worker stub with graceful SIGTERM shutdown, structured logging,
activity registration per agent, and health endpoint.
"""
from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class WorkerState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    DRAINING = "draining"
    STOPPED = "stopped"


@dataclass
class ActivityRegistration:
    """Registered activity with its agent and handler."""
    name: str
    agent_id: str
    handler: Optional[Callable] = None
    registered_at: float = field(default_factory=time.time)


@dataclass
class WorkerHealth:
    """Health status of the worker."""
    state: WorkerState
    uptime_seconds: float
    activities_registered: int
    active_tasks: int
    last_heartbeat: float


class Worker:
    """Temporal worker with lifecycle management.

    Stub implementation for development. In production, wraps temporalio.worker.Worker.
    """

    def __init__(
        self,
        task_queue: str = "labelforge-tasks",
        namespace: str = "default",
        host: str = "localhost:7233",
        max_concurrent_activities: int = 10,
    ) -> None:
        self._task_queue = task_queue
        self._namespace = namespace
        self._host = host
        self._max_concurrent = max_concurrent_activities
        self._state = WorkerState.IDLE
        self._started_at: Optional[float] = None
        self._activities: Dict[str, ActivityRegistration] = {}
        self._active_tasks = 0
        self._last_heartbeat = time.time()
        self._shutdown_requested = False

    @property
    def state(self) -> WorkerState:
        return self._state

    @property
    def task_queue(self) -> str:
        return self._task_queue

    def register_activity(
        self,
        name: str,
        agent_id: str,
        handler: Optional[Callable] = None,
    ) -> ActivityRegistration:
        """Register an activity for a specific agent."""
        if self._state not in (WorkerState.IDLE, WorkerState.RUNNING):
            raise RuntimeError(f"Cannot register activities in state {self._state}")

        reg = ActivityRegistration(name=name, agent_id=agent_id, handler=handler)
        self._activities[name] = reg
        logger.info(
            "Registered activity: %s (agent=%s) on queue=%s",
            name, agent_id, self._task_queue,
        )
        return reg

    def get_activities(self, agent_id: Optional[str] = None) -> List[ActivityRegistration]:
        """Get registered activities, optionally filtered by agent."""
        activities = list(self._activities.values())
        if agent_id:
            activities = [a for a in activities if a.agent_id == agent_id]
        return activities

    async def start(self) -> None:
        """Start the worker."""
        if self._state != WorkerState.IDLE:
            raise RuntimeError(f"Worker cannot start from state {self._state}")

        self._state = WorkerState.STARTING
        logger.info(
            "Starting worker: queue=%s namespace=%s host=%s activities=%d",
            self._task_queue, self._namespace, self._host, len(self._activities),
        )

        # Register signal handlers for graceful shutdown
        self._install_signal_handlers()

        self._state = WorkerState.RUNNING
        self._started_at = time.time()
        self._last_heartbeat = time.time()

        logger.info("Worker started successfully")

    async def stop(self, graceful: bool = True) -> None:
        """Stop the worker.

        If graceful=True, drains in-flight tasks before stopping.
        """
        if self._state == WorkerState.STOPPED:
            return

        if graceful:
            self._state = WorkerState.DRAINING
            logger.info("Worker draining — waiting for %d active tasks", self._active_tasks)
            # In production: wait for in-flight activities to complete
        else:
            logger.info("Worker force stopping")

        self._state = WorkerState.STOPPED
        self._shutdown_requested = True
        logger.info("Worker stopped")

    def _install_signal_handlers(self) -> None:
        """Install SIGTERM handler for graceful shutdown."""
        def handle_sigterm(signum, frame):
            logger.info("SIGTERM received — initiating graceful shutdown")
            self._shutdown_requested = True
            self._state = WorkerState.DRAINING

        try:
            signal.signal(signal.SIGTERM, handle_sigterm)
        except (OSError, ValueError):
            # Can't set signal handlers in non-main thread
            logger.debug("Cannot install signal handlers (not main thread)")

    def health(self) -> WorkerHealth:
        """Return current health status."""
        uptime = 0.0
        if self._started_at:
            uptime = time.time() - self._started_at

        return WorkerHealth(
            state=self._state,
            uptime_seconds=round(uptime, 2),
            activities_registered=len(self._activities),
            active_tasks=self._active_tasks,
            last_heartbeat=self._last_heartbeat,
        )

    def heartbeat(self) -> None:
        """Record a heartbeat timestamp."""
        self._last_heartbeat = time.time()
