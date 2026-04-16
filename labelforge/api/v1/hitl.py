"""HiTL (Human-in-the-Loop) thread endpoints — REST + WebSocket.

Sprint-14 adds:

* ``POST  /hitl/threads``                   — create thread (agent-callable)
* ``GET   /hitl/threads/{id}/messages``     — paginated message list
* ``POST  /hitl/threads/{id}/option-select``— record UI option click
* ``POST  /hitl/threads/{id}/resolve``      — close thread, resume workflow
* ``POST  /hitl/threads/{id}/escalate``     — escalate to PagerDuty/Slack
* ``WS    /hitl/threads/{id}/live``         — realtime event stream

The lifecycle logic lives in :mod:`labelforge.services.hitl`; this module is
the thin transport layer. All writes publish events through the
:class:`MessageRouter` so any connected WebSocket learns instantly.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from labelforge.api.v1.auth import get_current_user
from labelforge.config import settings
from labelforge.contracts import HiTLMessage, HiTLThread
from labelforge.core.auth import AuthError, TokenPayload, decode_token
from labelforge.db import session as _session_mod
from labelforge.db.models import HiTLMessageModel, HiTLThreadModel
from labelforge.db.session import get_db
from labelforge.services.hitl import (
    Priority,
    ThreadStatus,
    get_message_router,
    get_thread_resolver,
    priority_sla_minutes,
)
from labelforge.services.hitl.resolver import (
    AddMessageRequest,
    CreateThreadRequest,
    ThreadStateError,
)
from labelforge.services.hitl.router import EventType, make_envelope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hitl", tags=["hitl"])


# ── Request models ───────────────────────────────────────────────────────────


class CreateThreadRequestBody(BaseModel):
    order_id: str
    item_no: str
    agent_id: str
    priority: str = Field(default=Priority.P2.value)
    initial_message: Optional[str] = None
    context: Optional[dict] = None


class CreateMessageRequest(BaseModel):
    sender_type: str = "human"
    content: str = Field(min_length=1)
    context: Optional[dict] = None


class ResolveThreadRequest(BaseModel):
    note: Optional[str] = None
    resume_context: Optional[dict] = None


class EscalateThreadRequest(BaseModel):
    reason: str = Field(min_length=1)


class OptionSelectRequest(BaseModel):
    option_index: int = Field(ge=0)
    option_value: Optional[str] = None


# ── Response models ──────────────────────────────────────────────────────────


class ThreadListResponse(BaseModel):
    threads: list[HiTLThread]
    total: int


class ThreadDetailResponse(BaseModel):
    thread: HiTLThread
    messages: list[HiTLMessage]


class MessageListResponse(BaseModel):
    messages: list[HiTLMessage]
    total: int


class ResolveResponse(BaseModel):
    thread: HiTLThread
    ok: bool = True


class EscalateResponse(BaseModel):
    thread: HiTLThread
    ok: bool = True


# ── Helpers ──────────────────────────────────────────────────────────────────


VALID_PRIORITIES = {p.value for p in Priority}
VALID_STATUSES = {s.value for s in ThreadStatus}


def _thread_to_contract(model: HiTLThreadModel) -> HiTLThread:
    return HiTLThread(
        thread_id=model.id,
        order_id=model.order_id,
        item_no=model.item_no,
        agent_id=model.agent_id,
        priority=model.priority,
        status=model.status,
        sla_deadline=model.sla_deadline,
        created_at=model.created_at,
    )


def _message_to_contract(model: HiTLMessageModel) -> HiTLMessage:
    return HiTLMessage(
        message_id=model.id,
        thread_id=model.thread_id,
        sender_type=model.sender_type,
        content=model.content,
        context=model.context,
        created_at=model.created_at,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads(
    status: Optional[str] = Query(None, description="Filter by status: OPEN, IN_PROGRESS, RESOLVED, ESCALATED"),
    priority: Optional[str] = Query(None, description="Filter by priority: P0, P1, P2"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadListResponse:
    """List HiTL threads with optional filtering."""
    query = select(HiTLThreadModel).where(HiTLThreadModel.tenant_id == _user.tenant_id)
    count_query = select(func.count()).select_from(HiTLThreadModel).where(HiTLThreadModel.tenant_id == _user.tenant_id)

    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        query = query.where(HiTLThreadModel.status == status)
        count_query = count_query.where(HiTLThreadModel.status == status)
    if priority:
        if priority not in VALID_PRIORITIES:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {priority}")
        query = query.where(HiTLThreadModel.priority == priority)
        count_query = count_query.where(HiTLThreadModel.priority == priority)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(HiTLThreadModel.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    threads = result.scalars().all()

    return ThreadListResponse(
        threads=[_thread_to_contract(t) for t in threads],
        total=total,
    )


@router.post("/threads", response_model=HiTLThread, status_code=201)
async def create_thread(
    body: CreateThreadRequestBody,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HiTLThread:
    """Create a new HiTL thread (agent- or ops-triggered).

    The thread's SLA deadline is derived from its priority: P0 = 15min,
    P1 = 60min, P2 = 240min. A ``status_update`` event is broadcast.
    """
    if body.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {body.priority}")

    resolver = get_thread_resolver()
    thread = await resolver.create_thread(
        db,
        CreateThreadRequest(
            tenant_id=_user.tenant_id,
            order_id=body.order_id,
            item_no=body.item_no,
            agent_id=body.agent_id,
            priority=body.priority,
            initial_message=body.initial_message,
            context=body.context,
        ),
    )
    return _thread_to_contract(thread)


@router.get("/threads/{thread_id}", response_model=ThreadDetailResponse)
async def get_thread(
    thread_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadDetailResponse:
    """Get a single HiTL thread with its messages."""
    result = await db.execute(
        select(HiTLThreadModel)
        .options(selectinload(HiTLThreadModel.messages))
        .where(HiTLThreadModel.id == thread_id, HiTLThreadModel.tenant_id == _user.tenant_id)
    )
    thread = result.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    return ThreadDetailResponse(
        thread=_thread_to_contract(thread),
        messages=[_message_to_contract(m) for m in thread.messages],
    )


@router.get("/threads/{thread_id}/messages", response_model=MessageListResponse)
async def list_messages(
    thread_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageListResponse:
    """Paginated message list for a thread — used for initial hydration."""
    # Confirm thread exists + tenant isolation.
    thread_result = await db.execute(
        select(HiTLThreadModel).where(
            HiTLThreadModel.id == thread_id,
            HiTLThreadModel.tenant_id == _user.tenant_id,
        )
    )
    if thread_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    count_q = (
        select(func.count())
        .select_from(HiTLMessageModel)
        .where(HiTLMessageModel.thread_id == thread_id)
    )
    total = (await db.execute(count_q)).scalar_one()

    msg_q = (
        select(HiTLMessageModel)
        .where(HiTLMessageModel.thread_id == thread_id)
        .order_by(HiTLMessageModel.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(msg_q)).scalars().all()
    return MessageListResponse(
        messages=[_message_to_contract(m) for m in rows],
        total=total,
    )


@router.post("/threads/{thread_id}/messages", response_model=HiTLMessage, status_code=201)
async def add_message(
    thread_id: str,
    body: CreateMessageRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HiTLMessage:
    """Add a message to a HiTL thread (human reply or agent callback).

    Broadcasts an ``agent_message`` or ``human_message`` event to all
    connected WebSocket subscribers. Returns 404 for missing threads and
    409 for terminal threads (RESOLVED / ESCALATED).
    """
    resolver = get_thread_resolver()
    try:
        message = await resolver.add_message(
            db,
            AddMessageRequest(
                tenant_id=_user.tenant_id,
                thread_id=thread_id,
                sender_type=body.sender_type,
                content=body.content,
                context=body.context,
                actor=_user.user_id,
            ),
        )
    except ThreadStateError as exc:
        msg = str(exc)
        if msg == "Thread not found":
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    return _message_to_contract(message)


@router.post("/threads/{thread_id}/option-select", response_model=HiTLMessage, status_code=201)
async def option_select(
    thread_id: str,
    body: OptionSelectRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HiTLMessage:
    """Record an option-button click from the UI.

    Persists a ``human`` message with ``context.action = 'option_selected'``
    and broadcasts an ``option_selected`` event.
    """
    resolver = get_thread_resolver()
    try:
        message = await resolver.record_option_select(
            db,
            tenant_id=_user.tenant_id,
            thread_id=thread_id,
            option_index=body.option_index,
            option_value=body.option_value,
            actor=_user.user_id,
        )
    except ThreadStateError as exc:
        msg = str(exc)
        if msg == "Thread not found":
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    return _message_to_contract(message)


@router.post("/threads/{thread_id}/resolve", response_model=ResolveResponse)
async def resolve_thread(
    thread_id: str,
    body: Optional[ResolveThreadRequest] = None,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResolveResponse:
    """Mark a thread as RESOLVED and resume any parked workflow."""
    body = body or ResolveThreadRequest()
    resolver = get_thread_resolver()
    try:
        thread = await resolver.resolve_thread(
            db,
            tenant_id=_user.tenant_id,
            thread_id=thread_id,
            actor=_user.user_id,
            resolution_note=body.note,
            resume_context=body.resume_context,
        )
    except ThreadStateError as exc:
        msg = str(exc)
        if msg == "Thread not found":
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    return ResolveResponse(thread=_thread_to_contract(thread))


@router.post("/threads/{thread_id}/escalate", response_model=EscalateResponse)
async def escalate_thread(
    thread_id: str,
    body: EscalateThreadRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EscalateResponse:
    """Escalate a thread to PagerDuty/Slack and mark it ESCALATED."""
    resolver = get_thread_resolver()
    try:
        thread = await resolver.escalate_thread(
            db,
            tenant_id=_user.tenant_id,
            thread_id=thread_id,
            reason=body.reason,
            actor=_user.user_id,
        )
    except ThreadStateError as exc:
        msg = str(exc)
        if msg == "Thread not found":
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    return EscalateResponse(thread=_thread_to_contract(thread))


# ── WebSocket: realtime event stream ────────────────────────────────────────


# Heartbeat window. Exposed as a module variable so tests can shrink it.
HEARTBEAT_SECONDS: float = 30.0


async def _load_thread_for_ws(
    thread_id: str, tenant_id: str
) -> Optional[HiTLThreadModel]:
    async with _session_mod.async_session_factory() as db:
        result = await db.execute(
            select(HiTLThreadModel).where(
                HiTLThreadModel.id == thread_id,
                HiTLThreadModel.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()


@router.websocket("/threads/{thread_id}/live")
async def thread_live_ws(
    websocket: WebSocket,
    thread_id: str,
    token: Optional[str] = Query(None, description="JWT (query-param for WS auth)"),
) -> None:
    """Realtime event pipe for a HiTL thread.

    Auth: JWT via ``?token=`` query param (WebSocket can't easily carry
    headers). Tenant isolation enforced against ``HiTLThreadModel.tenant_id``
    before the socket is accepted — invalid/expired tokens close 4401;
    unknown or cross-tenant threads close 4404.

    Wire protocol — server → client envelopes::

        {"type": "hello",            "thread_id": ..., "ts": ...}
        {"type": "agent_message",    "thread_id": ..., "payload": {...}, "ts": ...}
        {"type": "human_message",    "thread_id": ..., "payload": {...}, "ts": ...}
        {"type": "status_update",    "thread_id": ..., "payload": {...}, "ts": ...}
        {"type": "thread_resolved",  "thread_id": ..., "payload": {...}, "ts": ...}
        {"type": "escalation",       "thread_id": ..., "payload": {...}, "ts": ...}
        {"type": "option_selected",  "thread_id": ..., "payload": {...}, "ts": ...}
        {"type": "typing",           "thread_id": ..., "payload": {...}, "ts": ...}
        {"type": "ping",             "ts": ...}

    Client → server frames::

        {"type": "message",         "content": "...",     "context": {...}}
        {"type": "option_selected", "option_index": 0,    "option_value": "..."}
        {"type": "typing"}
        {"type": "ping"}  /  {"type": "pong"}
    """
    if not token:
        await websocket.close(code=4401)
        return
    try:
        payload = decode_token(token, settings.jwt_secret_key)
    except AuthError:
        await websocket.close(code=4401)
        return

    thread = await _load_thread_for_ws(thread_id, payload.tenant_id)
    if thread is None:
        await websocket.close(code=4404)
        return

    await websocket.accept()

    router = get_message_router()
    subscription = router.subscribe(thread_id)
    last_client_activity = asyncio.get_event_loop().time()

    async def _recv_loop() -> None:
        nonlocal last_client_activity
        try:
            while True:
                msg = await websocket.receive_json()
                last_client_activity = asyncio.get_event_loop().time()
                await _handle_client_frame(msg, websocket, thread, payload)
        except WebSocketDisconnect:
            return
        except Exception as exc:  # malformed frame — best-effort error reply
            logger.debug("WS recv error: %s", exc)

    async def _fan_out_loop() -> None:
        try:
            async for envelope in subscription:
                await websocket.send_json(envelope)
        except Exception as exc:  # pragma: no cover
            logger.debug("WS send error: %s", exc)

    async def _heartbeat_loop() -> None:
        nonlocal last_client_activity
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            try:
                await websocket.send_json({"type": EventType.PING, "ts": datetime.now(timezone.utc).isoformat()})
            except Exception:
                return
            # Disconnect stale clients (no traffic for 2x heartbeat).
            if asyncio.get_event_loop().time() - last_client_activity > HEARTBEAT_SECONDS * 2:
                try:
                    await websocket.close(code=4408)  # request timeout
                except Exception:
                    pass
                return

    # Initial hello with current status.
    await websocket.send_json(make_envelope(
        "hello",
        thread_id,
        {
            "status": thread.status,
            "priority": thread.priority,
            "agent_id": thread.agent_id,
            "order_id": thread.order_id,
            "item_no": thread.item_no,
        },
    ))

    recv_task = asyncio.create_task(_recv_loop())
    fan_task = asyncio.create_task(_fan_out_loop())
    hb_task = asyncio.create_task(_heartbeat_loop())

    try:
        done, pending = await asyncio.wait(
            {recv_task, fan_task, hb_task}, return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in pending:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
    finally:
        await subscription.unsubscribe()
        try:
            await websocket.close()
        except Exception:
            pass


async def _handle_client_frame(
    msg: Any, websocket: WebSocket, thread: HiTLThreadModel, payload: TokenPayload,
) -> None:
    """Handle one incoming WS frame.

    Persists side-effects via the resolver so REST + WS writes go through
    the same lifecycle logic. Errors are reported back to the sending
    client only (no fan-out) via ``{"type": "error", ...}``.
    """
    if not isinstance(msg, dict):
        await websocket.send_json({"type": "error", "detail": "invalid frame"})
        return

    kind = msg.get("type")
    resolver = get_thread_resolver()

    if kind == "ping":
        await websocket.send_json({"type": "pong", "ts": datetime.now(timezone.utc).isoformat()})
        return
    if kind == "pong":
        # Client responding to server heartbeat — the recv loop already
        # refreshed last_client_activity.
        return

    if kind == "message":
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            await websocket.send_json({"type": "error", "detail": "empty message"})
            return
        sender_type = msg.get("sender_type", "human")
        if sender_type not in ("human", "agent", "system"):
            await websocket.send_json({"type": "error", "detail": f"bad sender_type: {sender_type}"})
            return
        async with _session_mod.async_session_factory() as db:
            try:
                await resolver.add_message(
                    db,
                    AddMessageRequest(
                        tenant_id=payload.tenant_id,
                        thread_id=thread.id,
                        sender_type=sender_type,
                        content=content,
                        context=msg.get("context"),
                        actor=payload.user_id,
                    ),
                )
            except ThreadStateError as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
        return

    if kind == "option_selected":
        idx = msg.get("option_index")
        if not isinstance(idx, int) or idx < 0:
            await websocket.send_json({"type": "error", "detail": "bad option_index"})
            return
        async with _session_mod.async_session_factory() as db:
            try:
                await resolver.record_option_select(
                    db,
                    tenant_id=payload.tenant_id,
                    thread_id=thread.id,
                    option_index=idx,
                    option_value=msg.get("option_value"),
                    actor=payload.user_id,
                )
            except ThreadStateError as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
        return

    if kind == "typing":
        # Fan out typing indicator to the rest of the thread. Don't persist.
        await get_message_router().publish(
            thread.id,
            make_envelope(
                EventType.TYPING,
                thread.id,
                {"actor": payload.user_id, "is_typing": bool(msg.get("is_typing", True))},
            ),
        )
        return

    await websocket.send_json({"type": "error", "detail": f"unknown frame type: {kind!r}"})
