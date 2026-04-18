"""HiTL (Human-in-the-Loop) services — thread resolver + message router.

This package implements Sprint-14:

* :class:`MessageRouter` — Redis pub/sub fan-out with an in-memory fallback
  used in tests / dev. All WebSocket subscribers for a thread share the
  router's channel; REST + WebSocket writers publish through it.
* :class:`ThreadResolver` — lifecycle service for ``HiTLThreadModel``:
  ``create_thread``, ``add_message``, ``resolve_thread``, ``escalate_thread``
  with SLA deadlines (P0: 15 min, P1: 1 hr, P2: 4 hr) and audit + workflow
  resume hooks.

Both services are accessed via module-level getters (``get_message_router``,
``get_thread_resolver``) so tests can swap in stubs without patching every
call site.
"""
from labelforge.services.hitl.router import (
    InMemoryMessageRouter,
    MessageRouter,
    RedisMessageRouter,
    get_message_router,
    set_message_router,
)
from labelforge.services.hitl.resolver import (
    ThreadResolver,
    get_thread_resolver,
    set_thread_resolver,
    priority_sla_minutes,
    Priority,
    ThreadStatus,
    set_escalation_notifier,
    set_workflow_resumer,
)
from labelforge.services.hitl.chat_dispatcher import (
    MAX_AGENT_TURNS,
    dispatch_on_human_message,
    get_auto_advance_hook,
    schedule_dispatch,
    set_auto_advance_hook,
)

__all__ = [
    "InMemoryMessageRouter",
    "MessageRouter",
    "RedisMessageRouter",
    "get_message_router",
    "set_message_router",
    "ThreadResolver",
    "get_thread_resolver",
    "set_thread_resolver",
    "priority_sla_minutes",
    "Priority",
    "ThreadStatus",
    "set_escalation_notifier",
    "set_workflow_resumer",
    # Chat dispatch
    "MAX_AGENT_TURNS",
    "dispatch_on_human_message",
    "get_auto_advance_hook",
    "schedule_dispatch",
    "set_auto_advance_hook",
]
