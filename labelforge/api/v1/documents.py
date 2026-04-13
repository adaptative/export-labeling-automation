"""Document endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, UploadFile, File
from pydantic import BaseModel, Field

from labelforge.api.v1.auth import get_current_user
from labelforge.contracts import DocumentClass
from labelforge.core.auth import TokenPayload

router = APIRouter(prefix="/documents", tags=["documents"])


# ── Response models ──────────────────────────────────────────────────────────


class Document(BaseModel):
    id: str
    order_id: str
    filename: str
    doc_class: DocumentClass
    storage_url: str
    page_count: int
    uploaded_at: datetime
    parsed: bool = False


class DocumentListResponse(BaseModel):
    documents: list[Document]
    total: int


class DocumentUploadResponse(BaseModel):
    id: str
    filename: str
    doc_class: DocumentClass
    message: str


# ── Mock data ────────────────────────────────────────────────────────────────

_MOCK_DOCS: list[Document] = [
    Document(
        id="doc-001",
        order_id="ORD-2026-0042",
        filename="PO-88210.pdf",
        doc_class=DocumentClass.PURCHASE_ORDER,
        storage_url="s3://labelforge-docs/ORD-2026-0042/PO-88210.pdf",
        page_count=4,
        uploaded_at=datetime(2026, 4, 8, 9, 5, 0, tzinfo=timezone.utc),
        parsed=True,
    ),
    Document(
        id="doc-002",
        order_id="ORD-2026-0042",
        filename="PI-88210.pdf",
        doc_class=DocumentClass.PROFORMA_INVOICE,
        storage_url="s3://labelforge-docs/ORD-2026-0042/PI-88210.pdf",
        page_count=2,
        uploaded_at=datetime(2026, 4, 8, 9, 6, 0, tzinfo=timezone.utc),
        parsed=True,
    ),
    Document(
        id="doc-003",
        order_id="ORD-2026-0043",
        filename="PO-77301.pdf",
        doc_class=DocumentClass.PURCHASE_ORDER,
        storage_url="s3://labelforge-docs/ORD-2026-0043/PO-77301.pdf",
        page_count=3,
        uploaded_at=datetime(2026, 4, 5, 11, 10, 0, tzinfo=timezone.utc),
        parsed=True,
    ),
    Document(
        id="doc-004",
        order_id="ORD-2026-0044",
        filename="warning-labels-batch.pdf",
        doc_class=DocumentClass.WARNING_LABELS,
        storage_url="s3://labelforge-docs/ORD-2026-0044/warning-labels-batch.pdf",
        page_count=1,
        uploaded_at=datetime(2026, 4, 9, 8, 30, 0, tzinfo=timezone.utc),
        parsed=False,
    ),
]


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    order_id: Optional[str] = Query(None, description="Filter by order ID"),
    doc_class: Optional[DocumentClass] = Query(None, description="Filter by document class"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
) -> DocumentListResponse:
    """List documents with optional filtering."""
    results = _MOCK_DOCS
    if order_id:
        results = [d for d in results if d.order_id == order_id]
    if doc_class is not None:
        results = [d for d in results if d.doc_class == doc_class]
    total = len(results)
    return DocumentListResponse(
        documents=results[offset : offset + limit], total=total
    )


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    order_id: str = Query(..., description="Order to attach document to"),
    file: UploadFile = File(...),
    _user: TokenPayload = Depends(get_current_user),
) -> DocumentUploadResponse:
    """Upload a document and classify it."""
    filename = file.filename or "unnamed.pdf"
    guessed_class = DocumentClass.UNKNOWN
    lower = filename.lower()
    if "po" in lower or "purchase" in lower:
        guessed_class = DocumentClass.PURCHASE_ORDER
    elif "pi" in lower or "proforma" in lower or "invoice" in lower:
        guessed_class = DocumentClass.PROFORMA_INVOICE
    elif "warning" in lower or "label" in lower:
        guessed_class = DocumentClass.WARNING_LABELS
    elif "protocol" in lower:
        guessed_class = DocumentClass.PROTOCOL
    elif "checklist" in lower:
        guessed_class = DocumentClass.CHECKLIST

    return DocumentUploadResponse(
        id="doc-new-001",
        filename=filename,
        doc_class=guessed_class,
        message=f"Document '{filename}' uploaded for order {order_id}. Classification pending confirmation.",
    )
