"""Order endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from labelforge.contracts import OrderItem, OrderState, ItemState

router = APIRouter(prefix="/orders", tags=["orders"])


# ── Response models ──────────────────────────────────────────────────────────


class OrderSummary(BaseModel):
    id: str
    importer_id: str
    po_number: str
    state: OrderState
    item_count: int
    created_at: datetime
    updated_at: datetime


class OrderDetail(OrderSummary):
    items: list[OrderItem]


class OrderListResponse(BaseModel):
    orders: list[OrderSummary]
    total: int


# ── Mock data ────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 4, 10, 14, 30, 0, tzinfo=timezone.utc)

_MOCK_ITEMS: list[OrderItem] = [
    OrderItem(
        id="item-001",
        order_id="ORD-2026-0042",
        item_no="A1001",
        state=ItemState.COMPLIANCE_EVAL,
        state_changed_at=_NOW,
        rules_snapshot_id="snap-r1",
    ),
    OrderItem(
        id="item-002",
        order_id="ORD-2026-0042",
        item_no="A1002",
        state=ItemState.FUSED,
        state_changed_at=_NOW,
        rules_snapshot_id="snap-r1",
    ),
    OrderItem(
        id="item-003",
        order_id="ORD-2026-0043",
        item_no="B2001",
        state=ItemState.DELIVERED,
        state_changed_at=_NOW,
        rules_snapshot_id="snap-r2",
    ),
]

_MOCK_ORDERS: list[OrderSummary] = [
    OrderSummary(
        id="ORD-2026-0042",
        importer_id="IMP-ACME",
        po_number="PO-88210",
        state=OrderState.IN_PROGRESS,
        item_count=2,
        created_at=datetime(2026, 4, 8, 9, 0, 0, tzinfo=timezone.utc),
        updated_at=_NOW,
    ),
    OrderSummary(
        id="ORD-2026-0043",
        importer_id="IMP-GLOBEX",
        po_number="PO-77301",
        state=OrderState.DELIVERED,
        item_count=1,
        created_at=datetime(2026, 4, 5, 11, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 9, 16, 0, 0, tzinfo=timezone.utc),
    ),
    OrderSummary(
        id="ORD-2026-0044",
        importer_id="IMP-ACME",
        po_number="PO-88215",
        state=OrderState.HUMAN_BLOCKED,
        item_count=3,
        created_at=datetime(2026, 4, 9, 8, 0, 0, tzinfo=timezone.utc),
        updated_at=_NOW,
    ),
]


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=OrderListResponse)
async def list_orders(
    state: Optional[OrderState] = Query(None, description="Filter by order state"),
    search: Optional[str] = Query(None, description="Search by PO number or order ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OrderListResponse:
    """List orders with optional filtering."""
    results = _MOCK_ORDERS
    if state is not None:
        results = [o for o in results if o.state == state]
    if search:
        q = search.lower()
        results = [
            o
            for o in results
            if q in o.id.lower() or q in o.po_number.lower()
        ]
    total = len(results)
    return OrderListResponse(orders=results[offset : offset + limit], total=total)


@router.get("/{order_id}", response_model=OrderDetail)
async def get_order(order_id: str) -> OrderDetail:
    """Get a single order by ID."""
    summary = next((o for o in _MOCK_ORDERS if o.id == order_id), None)
    if summary is None:
        summary = _MOCK_ORDERS[0]
    items = [i for i in _MOCK_ITEMS if i.order_id == summary.id]
    return OrderDetail(**summary.model_dump(), items=items)


@router.get("/{order_id}/items", response_model=list[OrderItem])
async def list_order_items(order_id: str) -> list[OrderItem]:
    """List all items belonging to an order."""
    return [i for i in _MOCK_ITEMS if i.order_id == order_id]
