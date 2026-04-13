"""Document endpoints — upload, list, preview, and classify.

Supports real file upload via BlobStore, background classification
via the Intake Classifier Agent, and document listing with filters.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from labelforge.api.v1.auth import get_current_user
from labelforge.contracts import DocumentClass
from labelforge.core.auth import TokenPayload
from labelforge.core.blobstore import BlobMeta, MemoryBlobStore
from labelforge.db.models import Document as DocumentModel, DocumentClassification, Order
from labelforge.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


# ── Shared store (in production, injected via DI) ─────────────────────────

_blob_store = MemoryBlobStore()


def get_blob_store() -> MemoryBlobStore:
    return _blob_store


# ── In-memory document registry (for BlobStore-backed features) ─────────────


class DocumentRecord(BaseModel):
    id: str
    order_id: str
    filename: str
    doc_class: str = DocumentClass.UNKNOWN.value
    confidence: float = 0.0
    storage_key: str
    content_hash: Optional[str] = None
    size_bytes: int = 0
    page_count: int = 0
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    classification_status: str = "pending"  # pending | classified | failed


_documents: list[DocumentRecord] = [
    DocumentRecord(
        id="doc-001",
        order_id="ORD-2026-0042",
        filename="PO-88210.pdf",
        doc_class=DocumentClass.PURCHASE_ORDER.value,
        confidence=0.98,
        storage_key="ORD-2026-0042/PO-88210.pdf",
        size_bytes=245_000,
        page_count=4,
        uploaded_at=datetime(2026, 4, 8, 9, 5, 0, tzinfo=timezone.utc),
        classification_status="classified",
    ),
    DocumentRecord(
        id="doc-002",
        order_id="ORD-2026-0042",
        filename="PI-88210.pdf",
        doc_class=DocumentClass.PROFORMA_INVOICE.value,
        confidence=0.96,
        storage_key="ORD-2026-0042/PI-88210.pdf",
        size_bytes=120_000,
        page_count=2,
        uploaded_at=datetime(2026, 4, 8, 9, 6, 0, tzinfo=timezone.utc),
        classification_status="classified",
    ),
    DocumentRecord(
        id="doc-003",
        order_id="ORD-2026-0043",
        filename="PO-77301.pdf",
        doc_class=DocumentClass.PURCHASE_ORDER.value,
        confidence=0.97,
        storage_key="ORD-2026-0043/PO-77301.pdf",
        size_bytes=198_000,
        page_count=3,
        uploaded_at=datetime(2026, 4, 5, 11, 10, 0, tzinfo=timezone.utc),
        classification_status="classified",
    ),
    DocumentRecord(
        id="doc-004",
        order_id="ORD-2026-0044",
        filename="warning-labels-batch.pdf",
        doc_class=DocumentClass.WARNING_LABELS.value,
        confidence=0.72,
        storage_key="ORD-2026-0044/warning-labels-batch.pdf",
        size_bytes=85_000,
        page_count=1,
        uploaded_at=datetime(2026, 4, 9, 8, 30, 0, tzinfo=timezone.utc),
        classification_status="classified",
    ),
]


# ── Response models ──────────────────────────────────────────────────────────


class DocumentResponse(BaseModel):
    id: str
    order_id: str
    filename: str
    doc_class: DocumentClass
    confidence: float
    size_bytes: int
    page_count: int
    uploaded_at: datetime
    classification_status: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


class DocumentUploadResponse(BaseModel):
    id: str
    filename: str
    doc_class: DocumentClass
    confidence: float
    size_bytes: int
    storage_key: str
    classification_status: str
    message: str


class DocumentDetailResponse(DocumentResponse):
    storage_key: str
    content_hash: Optional[str] = None


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


def _classify_by_filename(filename: str) -> tuple[str, float]:
    """Quick filename-based classification heuristic."""
    lower = filename.lower()
    if "po" in lower or "purchase" in lower:
        return DocumentClass.PURCHASE_ORDER.value, 0.60
    if "pi" in lower or "proforma" in lower or "invoice" in lower:
        return DocumentClass.PROFORMA_INVOICE.value, 0.60
    if "protocol" in lower:
        return DocumentClass.PROTOCOL.value, 0.60
    if "warning" in lower or "label" in lower:
        return DocumentClass.WARNING_LABELS.value, 0.55
    if "checklist" in lower or "check" in lower:
        return DocumentClass.CHECKLIST.value, 0.55
    return DocumentClass.UNKNOWN.value, 0.0


def _doc_to_response(doc: DocumentModel, classification: Optional[DocumentClassification]) -> DocumentResponse:
    """Convert a DB document + optional classification to response model."""
    doc_class = DocumentClass.UNKNOWN
    confidence = 0.0
    classification_status = "pending"
    if classification is not None:
        doc_class = DocumentClass(classification.doc_class)
        confidence = classification.confidence or 0.0
        classification_status = "classified"

    return DocumentResponse(
        id=doc.id,
        order_id=doc.order_id,
        filename=doc.filename,
        doc_class=doc_class,
        confidence=confidence,
        size_bytes=doc.size_bytes or 0,
        page_count=0,
        uploaded_at=doc.uploaded_at,
        classification_status=classification_status,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    order_id: Optional[str] = Query(None, description="Filter by order ID"),
    doc_class: Optional[str] = Query(None, description="Filter by document class"),
    classification_status: Optional[str] = Query(None, description="Filter by classification status"),
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
        stmt = stmt.where(dc.doc_class == doc_class)

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
        count_stmt = count_stmt.where(dc.doc_class == doc_class)

    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    stmt = stmt.order_by(DocumentModel.uploaded_at.desc()).offset(offset).limit(limit)

    result = await db.execute(stmt)
    rows = result.all()

    documents = [_doc_to_response(doc, classification) for doc, classification in rows]

    return DocumentListResponse(documents=documents, total=total)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: str,
    _user: TokenPayload = Depends(get_current_user),
) -> DocumentDetailResponse:
    """Get a single document by ID."""
    doc = next((d for d in _documents if d.id == document_id), None)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentDetailResponse(
        id=doc.id,
        order_id=doc.order_id,
        filename=doc.filename,
        doc_class=doc.doc_class,
        confidence=doc.confidence,
        size_bytes=doc.size_bytes,
        page_count=doc.page_count,
        uploaded_at=doc.uploaded_at,
        classification_status=doc.classification_status,
        storage_key=doc.storage_key,
        content_hash=doc.content_hash,
    )


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    order_id: str = Query(..., description="Order to attach document to"),
    file: UploadFile = File(...),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentUploadResponse:
    """Upload a document, store in BlobStore, and queue classification.

    The file is stored immediately. Classification runs asynchronously
    via the Intake Classifier Agent. Poll GET /documents/{id} to check
    classification_status.
    """
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
    content = await file.read()
    size_bytes = len(content)

    if size_bytes == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if size_bytes > 25 * 1024 * 1024:  # 25 MB limit
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit")

    # Store in BlobStore
    doc_id = f"doc-{uuid.uuid4().hex[:8]}"
    storage_key = f"{order_id}/{filename}"

    store = get_blob_store()
    blob_meta: BlobMeta = await store.upload(
        key=storage_key,
        data=content,
        content_type=file.content_type,
    )

    # Quick filename-based classification (real LLM classification is async)
    quick_class, quick_confidence = _classify_by_filename(filename)

    # Create DB record
    new_doc = DocumentModel(
        id=doc_id,
        tenant_id=_user.tenant_id,
        order_id=order_id,
        filename=filename,
        s3_key=storage_key,
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
        confidence=quick_confidence,
    )
    db.add(classification)
    await db.commit()

    # Also track in in-memory registry for BlobStore features
    doc_record = DocumentRecord(
        id=doc_id,
        order_id=order_id,
        filename=filename,
        doc_class=quick_class,
        confidence=quick_confidence,
        storage_key=storage_key,
        content_hash=blob_meta.sha256,
        size_bytes=size_bytes,
        page_count=0,
        classification_status="pending",
    )
    _documents.append(doc_record)

    logger.info(
        "Document uploaded: id=%s order=%s file=%s size=%d hash=%s",
        doc_id, order_id, filename, size_bytes, blob_meta.sha256[:16],
    )

    return DocumentUploadResponse(
        id=doc_id,
        filename=filename,
        doc_class=quick_class,
        confidence=quick_confidence,
        size_bytes=size_bytes,
        storage_key=storage_key,
        classification_status="pending",
        message=f"Document '{filename}' uploaded for order {order_id}. Classification pending.",
    )


@router.get("/{document_id}/preview")
async def preview_document(
    document_id: str,
    _user: TokenPayload = Depends(get_current_user),
) -> Response:
    """Download/preview document content from BlobStore."""
    doc = next((d for d in _documents if d.id == document_id), None)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    store = get_blob_store()
    try:
        data = await store.download(doc.storage_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="Document file not found in storage")

    content_type = "application/pdf"
    if doc.filename.lower().endswith((".xlsx", ".xls")):
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif doc.filename.lower().endswith((".png",)):
        content_type = "image/png"
    elif doc.filename.lower().endswith((".jpg", ".jpeg")):
        content_type = "image/jpeg"

    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
    )


@router.post("/{document_id}/classify", response_model=DocumentResponse)
async def classify_document(
    document_id: str,
    _user: TokenPayload = Depends(get_current_user),
) -> DocumentResponse:
    """Trigger classification for a document using the Intake Classifier Agent.

    In production, this would be called automatically after upload.
    This endpoint allows manual re-classification.
    """
    doc = next((d for d in _documents if d.id == document_id), None)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Try to read content from blob store for classification
    store = get_blob_store()
    doc_content = ""
    try:
        data = await store.download(doc.storage_key)
        doc_content = data.decode("utf-8", errors="replace")[:2000]
    except (KeyError, Exception):
        logger.warning("Could not read document content for classification: %s", document_id)

    try:
        from labelforge.agents.intake_classifier import IntakeClassifierAgent
        from labelforge.core.llm import OpenAIProvider
        from labelforge.config import settings as app_settings

        provider = OpenAIProvider(api_key=app_settings.openai_api_key)
        agent = IntakeClassifierAgent(provider)
        result = await agent.execute({
            "document_content": doc_content,
            "filename": doc.filename,
        })

        doc.doc_class = result.data.get("doc_class", DocumentClass.UNKNOWN.value)
        doc.confidence = result.confidence
        doc.classification_status = "classified"

    except Exception as exc:
        logger.error("Classification failed for %s: %s", document_id, exc)
        doc.classification_status = "failed"

    return DocumentResponse(
        id=doc.id,
        order_id=doc.order_id,
        filename=doc.filename,
        doc_class=doc.doc_class,
        confidence=doc.confidence,
        size_bytes=doc.size_bytes,
        page_count=doc.page_count,
        uploaded_at=doc.uploaded_at,
        classification_status=doc.classification_status,
    )
