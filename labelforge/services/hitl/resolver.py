"""HiTL ThreadResolver — thread lifecycle operations.

Responsibilities
----------------
* Create a new :class:`HiTLThreadModel` with a priority-derived SLA deadline.
* Persist incoming agent / human messages (:class:`HiTLMessageModel`).
* Transition threads OPEN → IN_PROGRESS → RESOLVED / ESCALATED.
* Publish realtime events via the configured :class:`MessageRouter` so any
  connected WebSocket clients learn about the change instantly.
* Write audit rows via :class:`AuditLog` and push notifications into the
  existing ``Notification`` table.
* Call pluggable escalation / workflow-resume hooks (PagerDuty/Slack stubs,
  Temporal signal). The defaults are no-ops so unit tests don't need any
  external wiring — the hooks are exposed via
  :func:`set_escalation_notifier` / :func:`set_workflow_resumer`.

SLA deadlines (from spec)
-------------------------
* P0 → 15 minutes
* P1 → 60 minutes
* P2 → 240 minutes
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.db.models import (
    AuditLog,
    HiTLMessageModel,
    HiTLThreadModel,
    Notification,
)
from labelforge.services.hitl.router import (
    EventType,
    MessageRouter,
    get_message_router,
    make_envelope,
)

logger = logging.getLogger(__name__)


# ── Enums ───────────────────────────────────────────────────────────────────


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class ThreadStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


# Terminal states — no further transitions allowed.
_TERMINAL: set[str] = {ThreadStatus.RESOLVED.value, ThreadStatus.ESCALATED.value}


SLA_MINUTES: dict[str, int] = {
    Priority.P0.value: 15,
    Priority.P1.value: 60,
    Priority.P2.value: 240,
}


class ThreadStateError(Exception):
    """Raised when a transition is rejected (e.g. resolving a resolved thread)."""


# ── Hooks — set by the worker/lifespan ──────────────────────────────────────


EscalationNotifier = Callable[[HiTLThreadModel, str], Awaitable[None]]
WorkflowResumer = Callable[[HiTLThreadModel, dict], Awaitable[None]]


async def _default_escalation_notifier(thread: HiTLThreadModel, reason: str) -> None:
    """No-op escalation notifier. Prod swaps in PagerDuty/Slack writers."""
    logger.info(
        "HiTL escalation (stub): thread=%s reason=%s priority=%s",
        thread.id, reason, thread.priority,
    )


async def _default_workflow_resumer(thread: HiTLThreadModel, context: dict) -> None:
    """No-op workflow resumer. Prod swaps in a Temporal signal sender."""
    logger.info(
        "HiTL workflow resume (stub): thread=%s order=%s item=%s context=%s",
        thread.id, thread.order_id, thread.item_no, context,
    )


_escalation_notifier: EscalationNotifier = _default_escalation_notifier
_workflow_resumer: WorkflowResumer = _default_workflow_resumer


def set_escalation_notifier(fn: Optional[EscalationNotifier]) -> None:
    """Install an escalation notifier (``None`` resets to default no-op)."""
    global _escalation_notifier
    _escalation_notifier = fn or _default_escalation_notifier


def set_workflow_resumer(fn: Optional[WorkflowResumer]) -> None:
    """Install a Temporal (or equivalent) workflow resumer."""
    global _workflow_resumer
    _workflow_resumer = fn or _default_workflow_resumer


# ── Helpers ─────────────────────────────────────────────────────────────────


def priority_sla_minutes(priority: str) -> int:
    """Return the SLA window in minutes for a thread priority."""
    if priority not in SLA_MINUTES:
        raise ValueError(f"Unknown priority: {priority!r}")
    return SLA_MINUTES[priority]


def compute_sla_deadline(priority: str, *, now: Optional[datetime] = None) -> datetime:
    """Compute the SLA deadline as (now + SLA minutes)."""
    now = now or datetime.now(timezone.utc)
    return now + timedelta(minutes=priority_sla_minutes(priority))


# ── Service ─────────────────────────────────────────────────────────────────


@dataclass
class CreateThreadRequest:
    tenant_id: str
    order_id: str
    item_no: str
    agent_id: str
    priority: str = Priority.P2.value
    initial_message: Optional[str] = None
    context: Optional[dict] = None


@dataclass
class AddMessageRequest:
    tenant_id: str
    thread_id: str
    sender_type: str  # "agent" | "human" | "system" | "drawing"
    content: str
    context: Optional[dict] = None
    actor: Optional[str] = None


class ThreadResolver:
    """Synchronous-API wrapper over HiTL lifecycle operations.

    The DB session and router are injected per call so the service is
    trivially testable (no global state coupling beyond the module-level
    singleton resolver, which itself is swappable).
    """

    def __init__(self, router: Optional[MessageRouter] = None) -> None:
        self._router_override = router

    @property
    def router(self) -> MessageRouter:
        return self._router_override or get_message_router()

    # ── Create ─────────────────────────────────────────────────────────

    async def create_thread(
        self,
        db: AsyncSession,
        req: CreateThreadRequest,
    ) -> HiTLThreadModel:
        if req.priority not in SLA_MINUTES:
            raise ValueError(f"Unknown priority: {req.priority!r}")

        thread = HiTLThreadModel(
            id=str(uuid4()),
            tenant_id=req.tenant_id,
            order_id=req.order_id,
            item_no=req.item_no,
            agent_id=req.agent_id,
            priority=req.priority,
            status=ThreadStatus.OPEN.value,
            sla_deadline=compute_sla_deadline(req.priority),
        )
        db.add(thread)
        await db.flush()

        if req.initial_message:
            msg = HiTLMessageModel(
                id=str(uuid4()),
                thread_id=thread.id,
                tenant_id=req.tenant_id,
                sender_type="agent",
                content=req.initial_message,
                context=req.context,
            )
            db.add(msg)

        db.add(AuditLog(
            id=str(uuid4()),
            tenant_id=req.tenant_id,
            user_id=None,
            actor=req.agent_id,
            actor_type="agent",
            action="hitl_thread_created",
            resource_type="hitl_thread",
            resource_id=thread.id,
            detail=f"Thread opened for order={req.order_id} item={req.item_no}",
            details={
                "priority": req.priority,
                "agent_id": req.agent_id,
                "sla_deadline": thread.sla_deadline.isoformat() if thread.sla_deadline else None,
            },
        ))
        await db.commit()
        await db.refresh(thread)

        await self.router.publish(
            thread.id,
            make_envelope(
                EventType.STATUS_UPDATE,
                thread.id,
                {
                    "status": thread.status,
                    "priority": thread.priority,
                    "sla_deadline": thread.sla_deadline.isoformat() if thread.sla_deadline else None,
                    "order_id": thread.order_id,
                    "item_no": thread.item_no,
                    "agent_id": thread.agent_id,
                },
            ),
        )
        if req.initial_message:
            await self.router.publish(
                thread.id,
                make_envelope(
                    EventType.AGENT_MESSAGE,
                    thread.id,
                    {
                        "sender_type": "agent",
                        "content": req.initial_message,
                        "context": req.context,
                    },
                ),
            )
        return thread

    # ── Add message ─────────────────────────────────────────────────────

    async def add_message(
        self,
        db: AsyncSession,
        req: AddMessageRequest,
    ) -> HiTLMessageModel:
        thread = await _load_thread(db, req.thread_id, req.tenant_id)
        if thread.status in _TERMINAL:
            raise ThreadStateError(
                f"Cannot add message to {thread.status.lower()} thread"
            )

        # First human reply transitions OPEN → IN_PROGRESS.
        if thread.status == ThreadStatus.OPEN.value and req.sender_type == "human":
            thread.status = ThreadStatus.IN_PROGRESS.value

        message = HiTLMessageModel(
            id=str(uuid4()),
            thread_id=thread.id,
            tenant_id=req.tenant_id,
            sender_type=req.sender_type,
            content=req.content,
            context=req.context,
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
        await db.refresh(thread)

        event_type = (
            EventType.HUMAN_MESSAGE if req.sender_type == "human"
            else EventType.AGENT_MESSAGE
        )
        await self.router.publish(
            thread.id,
            make_envelope(
                event_type,
                thread.id,
                {
                    "message_id": message.id,
                    "sender_type": message.sender_type,
                    "content": message.content,
                    "context": message.context,
                    "actor": req.actor,
                    "created_at": message.created_at.isoformat() if message.created_at else None,
                },
            ),
        )
        if thread.status == ThreadStatus.IN_PROGRESS.value:
            # Always broadcast so subscribers see the transition even if
            # they missed the prior OPEN status. Cheap and idempotent.
            await self.router.publish(
                thread.id,
                make_envelope(
                    EventType.STATUS_UPDATE,
                    thread.id,
                    {"status": thread.status},
                ),
            )

        return message

    # ── Resolve ─────────────────────────────────────────────────────────

    async def resolve_thread(
        self,
        db: AsyncSession,
        *,
        tenant_id: str,
        thread_id: str,
        actor: Optional[str] = None,
        resolution_note: Optional[str] = None,
        resume_context: Optional[dict] = None,
    ) -> HiTLThreadModel:
        thread = await _load_thread(db, thread_id, tenant_id)
        if thread.status in _TERMINAL:
            raise ThreadStateError(
                f"Thread already {thread.status.lower()}"
            )

        thread.status = ThreadStatus.RESOLVED.value
        thread.resolved_at = datetime.now(timezone.utc)

        if resolution_note:
            db.add(HiTLMessageModel(
                id=str(uuid4()),
                thread_id=thread.id,
                tenant_id=tenant_id,
                sender_type="system",
                content=resolution_note,
                context={"action": "resolve", "actor": actor},
            ))

        db.add(AuditLog(
            id=str(uuid4()),
            tenant_id=tenant_id,
            user_id=None,
            actor=actor or "system",
            actor_type="human" if actor else "system",
            action="hitl_thread_resolved",
            resource_type="hitl_thread",
            resource_id=thread.id,
            detail=resolution_note or "Thread resolved",
            details={"priority": thread.priority},
        ))
        await db.commit()
        await db.refresh(thread)

        # Resume any parked Temporal workflow — best-effort, never fatal.
        try:
            await _workflow_resumer(thread, resume_context or {})
        except Exception as exc:  # pragma: no cover — hook failures are logged
            logger.warning("workflow resume hook failed: %s", exc)

        await self.router.publish(
            thread.id,
            make_envelope(
                EventType.THREAD_RESOLVED,
                thread.id,
                {
                    "status": thread.status,
                    "actor": actor,
                    "note": resolution_note,
                    "resolved_at": thread.resolved_at.isoformat() if thread.resolved_at else None,
                },
            ),
        )
        return thread

    # ── Escalate ────────────────────────────────────────────────────────

    async def escalate_thread(
        self,
        db: AsyncSession,
        *,
        tenant_id: str,
        thread_id: str,
        reason: str,
        actor: Optional[str] = None,
    ) -> HiTLThreadModel:
        thread = await _load_thread(db, thread_id, tenant_id)
        if thread.status in _TERMINAL:
            raise ThreadStateError(
                f"Thread already {thread.status.lower()}"
            )

        thread.status = ThreadStatus.ESCALATED.value

        db.add(HiTLMessageModel(
            id=str(uuid4()),
            thread_id=thread.id,
            tenant_id=tenant_id,
            sender_type="system",
            content=f"Escalated: {reason}",
            context={"action": "escalate", "actor": actor, "reason": reason},
        ))
        db.add(AuditLog(
            id=str(uuid4()),
            tenant_id=tenant_id,
            user_id=None,
            actor=actor or "system",
            actor_type="human" if actor else "system",
            action="hitl_thread_escalated",
            resource_type="hitl_thread",
            resource_id=thread.id,
            detail=reason,
            details={"priority": thread.priority},
        ))
        # Drop a notification for on-call visibility.
        db.add(Notification(
            id=str(uuid4()),
            tenant_id=tenant_id,
            user_id=None,
            type="hitl_escalation",
            title=f"HiTL thread escalated: {thread.order_id} / item {thread.item_no}",
            body=reason,
            level="warning",
            order_id=thread.order_id,
            item_no=thread.item_no,
        ))
        await db.commit()
        await db.refresh(thread)

        # External escalation channels — best-effort.
        try:
            await _escalation_notifier(thread, reason)
        except Exception as exc:  # pragma: no cover — hook failures are logged
            logger.warning("escalation notifier failed: %s", exc)

        await self.router.publish(
            thread.id,
            make_envelope(
                EventType.ESCALATION,
                thread.id,
                {
                    "status": thread.status,
                    "reason": reason,
                    "actor": actor,
                    "priority": thread.priority,
                },
            ),
        )
        return thread

    # ── Option select (UI → agent) ──────────────────────────────────────

    async def record_option_select(
        self,
        db: AsyncSession,
        *,
        tenant_id: str,
        thread_id: str,
        option_index: int,
        option_value: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> HiTLMessageModel:
        thread = await _load_thread(db, thread_id, tenant_id)
        if thread.status in _TERMINAL:
            raise ThreadStateError(
                f"Cannot select option on {thread.status.lower()} thread"
            )

        content = (
            f"Selected option {option_index}"
            + (f": {option_value}" if option_value else "")
        )
        message = HiTLMessageModel(
            id=str(uuid4()),
            thread_id=thread.id,
            tenant_id=tenant_id,
            sender_type="human",
            content=content,
            context={
                "action": "option_selected",
                "option_index": option_index,
                "option_value": option_value,
                "actor": actor,
            },
        )
        db.add(message)

        # First option-select also flips OPEN → IN_PROGRESS.
        if thread.status == ThreadStatus.OPEN.value:
            thread.status = ThreadStatus.IN_PROGRESS.value

        await db.commit()
        await db.refresh(message)
        await db.refresh(thread)

        await self.router.publish(
            thread.id,
            make_envelope(
                EventType.OPTION_SELECTED,
                thread.id,
                {
                    "message_id": message.id,
                    "option_index": option_index,
                    "option_value": option_value,
                    "actor": actor,
                },
            ),
        )
        return message


# ── DB helpers ──────────────────────────────────────────────────────────────


async def _load_thread(
    db: AsyncSession, thread_id: str, tenant_id: str
) -> HiTLThreadModel:
    result = await db.execute(
        select(HiTLThreadModel).where(
            HiTLThreadModel.id == thread_id,
            HiTLThreadModel.tenant_id == tenant_id,
        )
    )
    thread = result.scalar_one_or_none()
    if thread is None:
        raise ThreadStateError("Thread not found")
    return thread


# ── Module-level singleton ──────────────────────────────────────────────────


_resolver: Optional[ThreadResolver] = None


def get_thread_resolver() -> ThreadResolver:
    global _resolver
    if _resolver is None:
        _resolver = ThreadResolver()
    return _resolver


def set_thread_resolver(resolver: Optional[ThreadResolver]) -> None:
    global _resolver
    _resolver = resolver
