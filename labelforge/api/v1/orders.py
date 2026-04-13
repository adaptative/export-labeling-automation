"""Order endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.contracts import (
    OrderItem,
    OrderState,
    ItemState,
    compute_order_state,
    OrderItem as ContractOrderItem,
)
from labelforge.core.auth import TokenPayload
from labelforge.db.models import Order, OrderItemModel
from labelforge.db.session import get_db

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


# ── Helpers ──────────────────────────────────────────────────────────────────


def _compute_state(items: list) -> OrderState:
    if not items:
        return OrderState.CREATED
    contract_items = [
        ContractOrderItem(
            id=i.id,
            order_id=i.order_id,
            item_no=i.item_no,
            state=i.state,
            state_changed_at=i.state_changed_at or datetime.now(tz=timezone.utc),
            rules_snapshot_id=i.rules_snapshot_id,
        )
        for i in items
    ]
    return compute_order_state(contract_items)


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=OrderListResponse)
async def list_orders(
    state: Optional[OrderState] = Query(None, description="Filter by order state"),
    search: Optional[str] = Query(None, description="Search by PO number or order ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderListResponse:
    """List orders with optional filtering."""
    # Fetch all orders for the tenant with their items eagerly loaded
    stmt = (
        select(Order)
        .where(Order.tenant_id == _user.tenant_id)
        .order_by(Order.created_at.desc())
    )

    if search:
        q = f"%{search}%"
        stmt = stmt.where(
            (Order.po_number.ilike(q)) | (Order.id.ilike(q))
        )

    result = await db.execute(stmt)
    orders = result.scalars().all()

    # Build summaries with computed state
    summaries: list[OrderSummary] = []
    for order in orders:
        items = order.items  # loaded via selectin relationship
        computed = _compute_state(items)

        # Apply state filter in Python since state is computed
        if state is not None and computed != state:
            continue

        summaries.append(
            OrderSummary(
                id=order.id,
                importer_id=order.importer_id,
                po_number=order.po_number or "",
                state=computed,
                item_count=len(items),
                created_at=order.created_at,
                updated_at=order.updated_at,
            )
        )

    total = len(summaries)
    return OrderListResponse(orders=summaries[offset : offset + limit], total=total)


@router.get("/{order_id}", response_model=OrderDetail)
async def get_order(
    order_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderDetail:
    """Get a single order by ID."""
    stmt = select(Order).where(
        Order.id == order_id,
        Order.tenant_id == _user.tenant_id,
    )
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    items = order.items
    computed = _compute_state(items)

    order_items = [
        OrderItem(
            id=i.id,
            order_id=i.order_id,
            item_no=i.item_no,
            state=i.state,
            state_changed_at=i.state_changed_at or datetime.now(tz=timezone.utc),
            rules_snapshot_id=i.rules_snapshot_id,
        )
        for i in items
    ]

    return OrderDetail(
        id=order.id,
        importer_id=order.importer_id,
        po_number=order.po_number or "",
        state=computed,
        item_count=len(items),
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=order_items,
    )


@router.get("/{order_id}/items", response_model=list[OrderItem])
async def list_order_items(
    order_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrderItem]:
    """List all items belonging to an order."""
    # Verify order exists
    order_check = await db.execute(
        select(Order.id).where(
            Order.id == order_id,
            Order.tenant_id == _user.tenant_id,
        )
    )
    if order_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    stmt = (
        select(OrderItemModel)
        .where(
            OrderItemModel.order_id == order_id,
            OrderItemModel.tenant_id == _user.tenant_id,
        )
        .order_by(OrderItemModel.item_no)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    return [
        OrderItem(
            id=i.id,
            order_id=i.order_id,
            item_no=i.item_no,
            state=i.state,
            state_changed_at=i.state_changed_at or datetime.now(tz=timezone.utc),
            rules_snapshot_id=i.rules_snapshot_id,
        )
        for i in items
    ]
