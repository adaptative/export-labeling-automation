"""Item endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.contracts import OrderItem, ItemState
from labelforge.core.auth import TokenPayload
from labelforge.db.models import OrderItemModel
from labelforge.db.session import get_db

router = APIRouter(prefix="/items", tags=["items"])


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=list[OrderItem])
async def list_items(
    state: Optional[ItemState] = Query(None, description="Filter by item state"),
    order_id: Optional[str] = Query(None, description="Filter by order ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrderItem]:
    """List all items with optional filtering."""
    stmt = (
        select(OrderItemModel)
        .where(OrderItemModel.tenant_id == _user.tenant_id)
    )

    if state is not None:
        stmt = stmt.where(OrderItemModel.state == state.value)

    if order_id:
        stmt = stmt.where(OrderItemModel.order_id == order_id)

    stmt = stmt.order_by(OrderItemModel.created_at.desc()).offset(offset).limit(limit)

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


@router.get("/{item_id}", response_model=OrderItem)
async def get_item(
    item_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderItem:
    """Get a single item by ID."""
    stmt = select(OrderItemModel).where(
        OrderItemModel.id == item_id,
        OrderItemModel.tenant_id == _user.tenant_id,
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()

    if item is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")

    return OrderItem(
        id=item.id,
        order_id=item.order_id,
        item_no=item.item_no,
        state=item.state,
        state_changed_at=item.state_changed_at or datetime.now(tz=timezone.utc),
        rules_snapshot_id=item.rules_snapshot_id,
    )
