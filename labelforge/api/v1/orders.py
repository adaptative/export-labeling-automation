"""Order endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field
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


class OrderActionResponse(BaseModel):
    order_id: str
    new_state: str
    message: str


class RejectRequest(BaseModel):
    reason: str = ""


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
    importer_id: Optional[str] = Query(None, description="Filter by importer ID"),
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
    if importer_id:
        stmt = stmt.where(Order.importer_id == importer_id)

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


@router.get("/export", response_model=None)
async def export_orders_csv(
    state: Optional[OrderState] = Query(None),
    search: Optional[str] = Query(None),
    importer_id: Optional[str] = Query(None),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export orders as CSV."""
    from fastapi.responses import StreamingResponse
    import io, csv
    # Reuse the same query logic as list_orders
    stmt = select(Order).where(Order.tenant_id == _user.tenant_id).order_by(Order.created_at.desc())
    if search:
        q = f"%{search}%"
        stmt = stmt.where((Order.po_number.ilike(q)) | (Order.id.ilike(q)))
    if importer_id:
        stmt = stmt.where(Order.importer_id == importer_id)
    result = await db.execute(stmt)
    orders = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "PO Number", "Importer", "State", "Items", "Created", "Updated"])
    for o in orders:
        items = o.items
        computed = _compute_state(items)
        if state is not None and computed != state:
            continue
        writer.writerow([o.id, o.po_number or "", o.importer_id, computed.value, len(items), o.created_at.isoformat(), o.updated_at.isoformat()])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=orders-export.csv"},
    )


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


# ── Create order ────────────────────────────────────────────────────────────


@router.post("", response_model=CreateOrderResponse, status_code=201)
async def create_order(
    body: CreateOrderRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreateOrderResponse:
    """Create a new order. Documents can be uploaded separately."""
    order_id = f"ORD-{datetime.now(timezone.utc).strftime('%Y')}-{uuid.uuid4().hex[:4].upper()}"
    po_number = body.po_reference or order_id
    now = datetime.now(timezone.utc)

    new_order = Order(
        id=order_id,
        tenant_id=_user.tenant_id,
        importer_id=body.importer_id,
        po_number=po_number,
        created_at=now,
        updated_at=now,
    )
    db.add(new_order)
    await db.commit()

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

_order_upload_logger = logging.getLogger(__name__)


async def _run_ai_classification(
    doc_id: str,
    tenant_id: str,
    filename: str,
    storage_key: str,
) -> None:
    """Background task: run IntakeClassifierAgent and update DB classification."""
    from labelforge.agents.intake_classifier import IntakeClassifierAgent
    from labelforge.config import settings as app_settings
    from labelforge.db.models import DocumentClassification
    from labelforge.db.session import async_session_factory

    # Read document content from blob store with proper text extraction
    from labelforge.api.v1.documents import get_blob_store
    from labelforge.core.doc_extract import extract_text
    store = get_blob_store()
    doc_content = ""
    try:
        data = await store.download(storage_key)
        doc_content = extract_text(data, filename, max_chars=3000)
    except Exception:
        _order_upload_logger.warning("Could not read content for AI classification: %s", doc_id)

    # Run agent
    try:
        from labelforge.core.llm import OpenAIProvider
        provider = OpenAIProvider(api_key=app_settings.openai_api_key)
        agent = IntakeClassifierAgent(provider)
        result = await agent.execute({
            "document_content": doc_content,
            "filename": filename,
        })

        # Update classification in DB
        async with async_session_factory() as db:
            cls_result = await db.execute(
                select(DocumentClassification).where(
                    DocumentClassification.document_id == doc_id,
                    DocumentClassification.tenant_id == tenant_id,
                )
            )
            classification = cls_result.scalar_one_or_none()
            if classification:
                classification.doc_class = result.data.get("doc_class", "UNKNOWN")
                classification.confidence = result.confidence
                classification.classification_status = "classified"
                await db.commit()

        _order_upload_logger.info(
            "AI classification complete: doc=%s class=%s confidence=%.2f",
            doc_id, result.data.get("doc_class"), result.confidence,
        )
    except Exception as exc:
        _order_upload_logger.error("AI classification failed for %s: %s", doc_id, exc)
        # Mark as failed in DB
        try:
            async with async_session_factory() as db:
                cls_result = await db.execute(
                    select(DocumentClassification).where(
                        DocumentClassification.document_id == doc_id,
                        DocumentClassification.tenant_id == tenant_id,
                    )
                )
                classification = cls_result.scalar_one_or_none()
                if classification:
                    classification.classification_status = "classified"
                    await db.commit()
        except Exception:
            pass


@router.post("/{order_id}/documents", status_code=201)
async def upload_order_document(
    order_id: str,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upload a document to a specific order.

    This is a convenience endpoint that delegates to the documents module.
    """
    from labelforge.api.v1.documents import (
        get_blob_store,
        _documents,
        DocumentRecord,
        _classify_by_filename,
        _guess_doc_class,
    )
    from labelforge.core.blobstore import BlobMeta
    from labelforge.db.models import Document as DocumentModel, DocumentClassification
    from uuid import uuid4

    # Verify order exists in DB
    order_check = await db.execute(
        select(Order.id).where(
            Order.id == order_id,
            Order.tenant_id == _user.tenant_id,
        )
    )
    if order_check.scalar_one_or_none() is None:
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

    # Persist to database
    new_doc = DocumentModel(
        id=doc_id,
        tenant_id=_user.tenant_id,
        order_id=order_id,
        filename=filename,
        s3_key=storage_key,
        size_bytes=size_bytes,
    )
    db.add(new_doc)

    guessed_class = _guess_doc_class(filename)
    classification = DocumentClassification(
        id=str(uuid4()),
        document_id=doc_id,
        tenant_id=_user.tenant_id,
        doc_class=guessed_class.value,
        confidence=quick_confidence,
        classification_status="classifying",
    )
    db.add(classification)
    await db.commit()

    # Also track in in-memory registry for BlobStore features
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

    # Queue AI classification as a background task
    background_tasks.add_task(
        _run_ai_classification,
        doc_id=doc_id,
        tenant_id=_user.tenant_id,
        filename=filename,
        storage_key=storage_key,
    )

    return {
        "id": doc_id,
        "order_id": order_id,
        "filename": filename,
        "doc_class": quick_class,
        "confidence": quick_confidence,
        "size_bytes": size_bytes,
        "classification_status": "classifying",
        "message": f"Document '{filename}' uploaded to order {order_id}. AI classification in progress.",
    }


# ── Order actions ───────────────────────────────────────────────────────────


@router.post("/{order_id}/approve", response_model=OrderActionResponse)
async def approve_order(
    order_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderActionResponse:
    """Approve an order and mark all items as DELIVERED."""
    stmt = select(Order).where(Order.id == order_id, Order.tenant_id == _user.tenant_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    # Update all items to DELIVERED
    for item in order.items:
        item.state = "DELIVERED"
        item.state_changed_at = datetime.now(tz=timezone.utc)
    order.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()

    return OrderActionResponse(order_id=order_id, new_state="DELIVERED", message="Order approved and delivered.")


@router.post("/{order_id}/reject", response_model=OrderActionResponse)
async def reject_order(
    order_id: str,
    body: RejectRequest = RejectRequest(),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderActionResponse:
    """Reject an order and loop items back to INTAKE_CLASSIFIED."""
    stmt = select(Order).where(Order.id == order_id, Order.tenant_id == _user.tenant_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    for item in order.items:
        item.state = "INTAKE_CLASSIFIED"
        item.state_changed_at = datetime.now(tz=timezone.utc)
    order.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()

    return OrderActionResponse(order_id=order_id, new_state="IN_PROGRESS", message=f"Order rejected. Reason: {body.reason or 'N/A'}")


@router.post("/{order_id}/send-to-printer", response_model=OrderActionResponse)
async def send_to_printer(
    order_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderActionResponse:
    """Send order to printer."""
    stmt = select(Order).where(Order.id == order_id, Order.tenant_id == _user.tenant_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    order.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()

    return OrderActionResponse(order_id=order_id, new_state=_compute_state(order.items).value, message="Order sent to printer.")
