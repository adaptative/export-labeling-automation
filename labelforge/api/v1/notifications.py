"""Notification endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

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


# ── Mock data ────────────────────────────────────────────────────────────────

_MOCK_NOTIFICATIONS: list[Notification] = [
    Notification(
        id="notif-001",
        type="hitl_escalation",
        title="HiTL Escalation: Prop 65 warning needed",
        message="Item A1001 in order ORD-2026-0042 requires human input to determine if Prop 65 warning applies. SLA deadline: 2026-04-11 14:30 UTC.",
        severity="high",
        order_id="ORD-2026-0042",
        item_no="A1001",
        read=False,
        created_at=datetime(2026, 4, 10, 14, 30, 0, tzinfo=timezone.utc),
    ),
    Notification(
        id="notif-002",
        type="compliance_fail",
        title="Compliance check failed for item C3001",
        message="FCC Part 15 declaration missing from carton layout for item C3001. Manual review required.",
        severity="high",
        order_id="ORD-2026-0044",
        item_no="C3001",
        read=False,
        created_at=datetime(2026, 4, 9, 16, 0, 0, tzinfo=timezone.utc),
    ),
    Notification(
        id="notif-003",
        type="order_delivered",
        title="Order ORD-2026-0043 delivered",
        message="All items in order ORD-2026-0043 have been marked as delivered. Approval PDFs are available for download.",
        severity="info",
        order_id="ORD-2026-0043",
        item_no=None,
        read=True,
        created_at=datetime(2026, 4, 9, 16, 0, 0, tzinfo=timezone.utc),
    ),
    Notification(
        id="notif-004",
        type="fusion_conflict",
        title="Data conflict detected during fusion",
        message="Net weight mismatch between PO (2.5 kg) and PI (3.1 kg) for item C3001. Fusion agent has opened a HiTL thread.",
        severity="medium",
        order_id="ORD-2026-0044",
        item_no="C3001",
        read=False,
        created_at=datetime(2026, 4, 9, 10, 5, 0, tzinfo=timezone.utc),
    ),
]


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    severity: Optional[str] = Query(None, description="Filter by severity: high, medium, low, info"),
    read: Optional[bool] = Query(None, description="Filter by read status"),
    order_id: Optional[str] = Query(None, description="Filter by order ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> NotificationListResponse:
    """List notifications with optional filtering."""
    results = _MOCK_NOTIFICATIONS
    if severity:
        results = [n for n in results if n.severity == severity]
    if read is not None:
        results = [n for n in results if n.read == read]
    if order_id:
        results = [n for n in results if n.order_id == order_id]
    total = len(results)
    unread = sum(1 for n in results if not n.read)
    return NotificationListResponse(
        notifications=results[offset : offset + limit],
        total=total,
        unread_count=unread,
    )
