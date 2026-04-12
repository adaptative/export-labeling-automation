"""Item endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query

from labelforge.contracts import OrderItem, ItemState

router = APIRouter(prefix="/items", tags=["items"])

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
    OrderItem(
        id="item-004",
        order_id="ORD-2026-0044",
        item_no="C3001",
        state=ItemState.HUMAN_BLOCKED,
        state_changed_at=_NOW,
        rules_snapshot_id="snap-r3",
    ),
]


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=list[OrderItem])
async def list_items(
    state: Optional[ItemState] = Query(None, description="Filter by item state"),
    order_id: Optional[str] = Query(None, description="Filter by order ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[OrderItem]:
    """List all items with optional filtering."""
    results = _MOCK_ITEMS
    if state is not None:
        results = [i for i in results if i.state == state]
    if order_id:
        results = [i for i in results if i.order_id == order_id]
    return results[offset : offset + limit]


@router.get("/{item_id}", response_model=OrderItem)
async def get_item(item_id: str) -> OrderItem:
    """Get a single item by ID."""
    item = next((i for i in _MOCK_ITEMS if i.id == item_id), None)
    if item is None:
        return _MOCK_ITEMS[0]
    return item
