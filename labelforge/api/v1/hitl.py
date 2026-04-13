"""HiTL (Human-in-the-Loop) thread endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from labelforge.api.v1.auth import get_current_user
from labelforge.contracts import HiTLMessage, HiTLThread
from labelforge.core.auth import TokenPayload
from labelforge.db.models import HiTLMessageModel, HiTLThreadModel
from labelforge.db.session import get_db

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


# ── Helpers ──────────────────────────────────────────────────────────────────


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
        query = query.where(HiTLThreadModel.status == status)
        count_query = count_query.where(HiTLThreadModel.status == status)
    if priority:
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


@router.post("/threads/{thread_id}/messages", response_model=HiTLMessage, status_code=201)
async def add_message(
    thread_id: str,
    body: CreateMessageRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HiTLMessage:
    """Add a message to a HiTL thread."""
    # Verify thread exists and belongs to tenant
    result = await db.execute(
        select(HiTLThreadModel).where(
            HiTLThreadModel.id == thread_id,
            HiTLThreadModel.tenant_id == _user.tenant_id,
        )
    )
    thread = result.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    message = HiTLMessageModel(
        id=str(uuid4()),
        thread_id=thread_id,
        tenant_id=_user.tenant_id,
        sender_type=body.sender_type,
        content=body.content,
        context=body.context,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    return _message_to_contract(message)
