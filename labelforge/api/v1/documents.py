"""Document endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from labelforge.api.v1.auth import get_current_user
from labelforge.contracts import DocumentClass
from labelforge.core.auth import TokenPayload
from labelforge.db.models import Document as DocumentModel, DocumentClassification, Order
from labelforge.db.session import get_db

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


# ── Helpers ──────────────────────────────────────────────────────────────────


def _guess_doc_class(filename: str) -> DocumentClass:
    """Guess document class from filename."""
    lower = filename.lower()
    if "po" in lower or "purchase" in lower:
        return DocumentClass.PURCHASE_ORDER
    elif "pi" in lower or "proforma" in lower or "invoice" in lower:
        return DocumentClass.PROFORMA_INVOICE
    elif "warning" in lower or "label" in lower:
        return DocumentClass.WARNING_LABELS
    elif "protocol" in lower:
        return DocumentClass.PROTOCOL
    elif "checklist" in lower:
        return DocumentClass.CHECKLIST
    return DocumentClass.UNKNOWN


def _doc_to_response(doc: DocumentModel, classification: Optional[DocumentClassification]) -> Document:
    """Convert a DB document + optional classification to response model."""
    doc_class = DocumentClass.UNKNOWN
    if classification is not None:
        doc_class = DocumentClass(classification.doc_class)

    return Document(
        id=doc.id,
        order_id=doc.order_id,
        filename=doc.filename,
        doc_class=doc_class,
        storage_url=f"s3://labelforge-docs/{doc.s3_key}",
        page_count=0,  # not stored in DB; would come from parsing
        uploaded_at=doc.uploaded_at,
        parsed=False,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    order_id: Optional[str] = Query(None, description="Filter by order ID"),
    doc_class: Optional[DocumentClass] = Query(None, description="Filter by document class"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    """List documents with optional filtering."""
    dc = aliased(DocumentClassification)

    stmt = (
        select(DocumentModel, dc)
        .outerjoin(dc, dc.document_id == DocumentModel.id)
        .where(DocumentModel.tenant_id == _user.tenant_id)
    )

    if order_id:
        stmt = stmt.where(DocumentModel.order_id == order_id)

    if doc_class is not None:
        stmt = stmt.where(dc.doc_class == doc_class.value)

    # Get total count before pagination
    count_stmt = (
        select(func.count())
        .select_from(DocumentModel)
        .outerjoin(dc, dc.document_id == DocumentModel.id)
        .where(DocumentModel.tenant_id == _user.tenant_id)
    )
    if order_id:
        count_stmt = count_stmt.where(DocumentModel.order_id == order_id)
    if doc_class is not None:
        count_stmt = count_stmt.where(dc.doc_class == doc_class.value)

    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    stmt = stmt.order_by(DocumentModel.uploaded_at.desc()).offset(offset).limit(limit)

    result = await db.execute(stmt)
    rows = result.all()

    documents = [_doc_to_response(doc, classification) for doc, classification in rows]

    return DocumentListResponse(documents=documents, total=total)


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    order_id: str = Query(..., description="Order to attach document to"),
    file: UploadFile = File(...),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentUploadResponse:
    """Upload a document and classify it."""
    # Verify order exists
    order_check = await db.execute(
        select(Order.id).where(
            Order.id == order_id,
            Order.tenant_id == _user.tenant_id,
        )
    )
    if order_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    filename = file.filename or "unnamed.pdf"
    doc_id = str(uuid4())
    s3_key = f"{order_id}/{filename}"

    # Read file content for size
    content = await file.read()
    size_bytes = len(content)

    # Create document record
    new_doc = DocumentModel(
        id=doc_id,
        tenant_id=_user.tenant_id,
        order_id=order_id,
        filename=filename,
        s3_key=s3_key,
        size_bytes=size_bytes,
    )
    db.add(new_doc)

    # Create initial classification
    guessed_class = _guess_doc_class(filename)
    classification = DocumentClassification(
        id=str(uuid4()),
        document_id=doc_id,
        tenant_id=_user.tenant_id,
        doc_class=guessed_class.value,
        confidence=0.5,  # filename-based guess gets low confidence
    )
    db.add(classification)

    await db.commit()

    return DocumentUploadResponse(
        id=doc_id,
        filename=filename,
        doc_class=guessed_class,
        message=f"Document '{filename}' uploaded for order {order_id}. Classification pending confirmation.",
    )
