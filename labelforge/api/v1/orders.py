"""Order endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field

from labelforge.api.v1.auth import get_current_user
from labelforge.contracts import OrderItem, OrderState, ItemState
from labelforge.core.auth import TokenPayload

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
    _user: TokenPayload = Depends(get_current_user),
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
async def get_order(order_id: str, _user: TokenPayload = Depends(get_current_user)) -> OrderDetail:
    """Get a single order by ID."""
    summary = next((o for o in _MOCK_ORDERS if o.id == order_id), None)
    if summary is None:
        summary = _MOCK_ORDERS[0]
    items = [i for i in _MOCK_ITEMS if i.order_id == summary.id]
    return OrderDetail(**summary.model_dump(), items=items)


@router.get("/{order_id}/items", response_model=list[OrderItem])
async def list_order_items(order_id: str, _user: TokenPayload = Depends(get_current_user)) -> list[OrderItem]:
    """List all items belonging to an order."""
    return [i for i in _MOCK_ITEMS if i.order_id == order_id]


# ── Request models ──────────────────────────────────────────────────────────


class CreateOrderRequest(BaseModel):
    importer_id: str = Field(..., min_length=1)
    po_reference: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None


class CreateOrderResponse(BaseModel):
    id: str
    importer_id: str
    po_number: str
    state: OrderState
    item_count: int
    created_at: datetime
    message: str


# ── Create order ────────────────────────────────────────────────────────────


@router.post("", response_model=CreateOrderResponse, status_code=201)
async def create_order(
    body: CreateOrderRequest,
    _user: TokenPayload = Depends(get_current_user),
) -> CreateOrderResponse:
    """Create a new order. Documents can be uploaded separately."""
    order_id = f"ORD-{datetime.now(timezone.utc).strftime('%Y')}-{uuid.uuid4().hex[:4].upper()}"
    po_number = body.po_reference or order_id
    now = datetime.now(timezone.utc)

    new_order = OrderSummary(
        id=order_id,
        importer_id=body.importer_id,
        po_number=po_number,
        state=OrderState.CREATED,
        item_count=0,
        created_at=now,
        updated_at=now,
    )
    _MOCK_ORDERS.append(new_order)

    return CreateOrderResponse(
        id=order_id,
        importer_id=body.importer_id,
        po_number=po_number,
        state=OrderState.CREATED,
        item_count=0,
        created_at=now,
        message=f"Order {order_id} created. Upload documents to start the pipeline.",
    )


# ── Order-scoped document upload ────────────────────────────────────────────


@router.post("/{order_id}/documents", status_code=201)
async def upload_order_document(
    order_id: str,
    file: UploadFile = File(...),
    _user: TokenPayload = Depends(get_current_user),
) -> dict:
    """Upload a document to a specific order.

    This is a convenience endpoint that delegates to the documents module.
    """
    from labelforge.api.v1.documents import (
        get_blob_store,
        _documents,
        DocumentRecord,
        _classify_by_filename,
    )
    from labelforge.core.blobstore import BlobMeta

    # Verify order exists
    order = next((o for o in _MOCK_ORDERS if o.id == order_id), None)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    filename = file.filename or "unnamed.pdf"
    content = await file.read()
    size_bytes = len(content)

    if size_bytes == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if size_bytes > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit")

    doc_id = f"doc-{uuid.uuid4().hex[:8]}"
    storage_key = f"{order_id}/{filename}"

    store = get_blob_store()
    blob_meta: BlobMeta = await store.upload(key=storage_key, data=content, content_type=file.content_type)

    quick_class, quick_confidence = _classify_by_filename(filename)

    doc = DocumentRecord(
        id=doc_id,
        order_id=order_id,
        filename=filename,
        doc_class=quick_class,
        confidence=quick_confidence,
        storage_key=storage_key,
        content_hash=blob_meta.sha256,
        size_bytes=size_bytes,
        classification_status="pending",
    )
    _documents.append(doc)

    return {
        "id": doc_id,
        "order_id": order_id,
        "filename": filename,
        "doc_class": quick_class,
        "confidence": quick_confidence,
        "size_bytes": size_bytes,
        "classification_status": "pending",
        "message": f"Document '{filename}' uploaded to order {order_id}. Classification pending.",
    }
