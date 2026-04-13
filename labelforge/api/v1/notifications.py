"""Notification endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.core.auth import TokenPayload
from labelforge.db.models import Notification as NotificationModel
from labelforge.db.session import get_db

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── Response models ──────────────────────────────────────────────────────────


class Notification(BaseModel):
    id: str
    type: str
    title: str
    message: str
    severity: str
    order_id: Optional[str] = None
    item_no: Optional[str] = None
    read: bool = False
    created_at: datetime


class NotificationListResponse(BaseModel):
    notifications: list[Notification]
    total: int
    unread_count: int


# ── Helpers ─────────────────────────────────────────────────────────────────


def _to_notification(n: NotificationModel) -> Notification:
    return Notification(
        id=n.id,
        type=n.type,
        title=n.title,
        message=n.body or "",
        severity=n.level,
        order_id=n.order_id,
        item_no=n.item_no,
        read=n.is_read,
        created_at=n.created_at,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    severity: Optional[str] = Query(None, description="Filter by severity: high, medium, low, info"),
    read: Optional[bool] = Query(None, description="Filter by read status"),
    order_id: Optional[str] = Query(None, description="Filter by order ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationListResponse:
    """List notifications with optional filtering."""
    query = select(NotificationModel)
    count_query = select(func.count()).select_from(NotificationModel)
    unread_query = select(func.count()).select_from(NotificationModel).where(
        NotificationModel.is_read == False  # noqa: E712
    )

    if severity:
        query = query.where(NotificationModel.level == severity)
        count_query = count_query.where(NotificationModel.level == severity)
        unread_query = unread_query.where(NotificationModel.level == severity)

    if read is not None:
        query = query.where(NotificationModel.is_read == read)
        count_query = count_query.where(NotificationModel.is_read == read)
        unread_query = unread_query.where(NotificationModel.is_read == read)

    if order_id:
        query = query.where(NotificationModel.order_id == order_id)
        count_query = count_query.where(NotificationModel.order_id == order_id)
        unread_query = unread_query.where(NotificationModel.order_id == order_id)

    # Execute counts
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    unread_result = await db.execute(unread_query)
    unread_count = unread_result.scalar_one()

    # Fetch paginated results
    query = query.order_by(NotificationModel.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    notifications = result.scalars().all()

    return NotificationListResponse(
        notifications=[_to_notification(n) for n in notifications],
        total=total,
        unread_count=unread_count,
    )
