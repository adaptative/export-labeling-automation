"""HiTL (Human-in-the-Loop) thread endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Query
from pydantic import BaseModel

from labelforge.contracts import HiTLThread, HiTLMessage

router = APIRouter(prefix="/hitl", tags=["hitl"])


# ── Request models ───────────────────────────────────────────────────────────


class CreateMessageRequest(BaseModel):
    sender_type: str = "human"
    content: str
    context: Optional[dict] = None


# ── Response models ──────────────────────────────────────────────────────────


class ThreadListResponse(BaseModel):
    threads: list[HiTLThread]
    total: int


class ThreadDetailResponse(BaseModel):
    thread: HiTLThread
    messages: list[HiTLMessage]


# ── Mock data ────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 4, 10, 14, 30, 0, tzinfo=timezone.utc)

_MOCK_THREADS: list[HiTLThread] = [
    HiTLThread(
        thread_id="hitl-001",
        order_id="ORD-2026-0042",
        item_no="A1001",
        agent_id="compliance-agent",
        priority="P0",
        status="OPEN",
        sla_deadline=datetime(2026, 4, 11, 14, 30, 0, tzinfo=timezone.utc),
        created_at=_NOW,
    ),
    HiTLThread(
        thread_id="hitl-002",
        order_id="ORD-2026-0044",
        item_no="C3001",
        agent_id="fusion-agent",
        priority="P1",
        status="IN_PROGRESS",
        sla_deadline=datetime(2026, 4, 12, 9, 0, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 4, 9, 10, 0, 0, tzinfo=timezone.utc),
    ),
    HiTLThread(
        thread_id="hitl-003",
        order_id="ORD-2026-0043",
        item_no="B2001",
        agent_id="validation-agent",
        priority="P2",
        status="RESOLVED",
        sla_deadline=None,
        created_at=datetime(2026, 4, 6, 15, 0, 0, tzinfo=timezone.utc),
    ),
]

_MOCK_MESSAGES: list[HiTLMessage] = [
    HiTLMessage(
        message_id="msg-001",
        thread_id="hitl-001",
        sender_type="agent",
        content="Prop 65 warning required for item A1001 but the destination state could not be determined. Please confirm the US destination state.",
        context={"rule_code": "PROP65", "item_no": "A1001"},
        created_at=_NOW,
    ),
    HiTLMessage(
        message_id="msg-002",
        thread_id="hitl-001",
        sender_type="human",
        content="Destination is California. Please apply Prop 65 warning label.",
        context=None,
        created_at=datetime(2026, 4, 10, 15, 0, 0, tzinfo=timezone.utc),
    ),
    HiTLMessage(
        message_id="msg-003",
        thread_id="hitl-002",
        sender_type="agent",
        content="PO line item C3001 lists net weight as 2.5 kg but PI shows 3.1 kg. Which value is correct?",
        context={"field": "net_weight", "po_value": "2.5", "pi_value": "3.1"},
        created_at=datetime(2026, 4, 9, 10, 5, 0, tzinfo=timezone.utc),
    ),
]


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads(
    status: Optional[str] = Query(None, description="Filter by status: OPEN, IN_PROGRESS, RESOLVED, ESCALATED"),
    priority: Optional[str] = Query(None, description="Filter by priority: P0, P1, P2"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ThreadListResponse:
    """List HiTL threads with optional filtering."""
    results = _MOCK_THREADS
    if status:
        results = [t for t in results if t.status == status]
    if priority:
        results = [t for t in results if t.priority == priority]
    total = len(results)
    return ThreadListResponse(threads=results[offset : offset + limit], total=total)


@router.get("/threads/{thread_id}", response_model=ThreadDetailResponse)
async def get_thread(thread_id: str) -> ThreadDetailResponse:
    """Get a single HiTL thread with its messages."""
    thread = next((t for t in _MOCK_THREADS if t.thread_id == thread_id), None)
    if thread is None:
        thread = _MOCK_THREADS[0]
    messages = [m for m in _MOCK_MESSAGES if m.thread_id == thread.thread_id]
    return ThreadDetailResponse(thread=thread, messages=messages)


@router.post("/threads/{thread_id}/messages", response_model=HiTLMessage, status_code=201)
async def add_message(thread_id: str, body: CreateMessageRequest) -> HiTLMessage:
    """Add a message to a HiTL thread."""
    return HiTLMessage(
        message_id=f"msg-{uuid4().hex[:8]}",
        thread_id=thread_id,
        sender_type=body.sender_type,
        content=body.content,
        context=body.context,
        created_at=datetime.now(tz=timezone.utc),
    )
