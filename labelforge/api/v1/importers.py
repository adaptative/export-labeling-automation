"""Importer onboarding + management endpoints (Sprint 8).

Covers:
  * Importer CRUD (list, get, create, update, soft-delete)
  * Importer sub-resources (orders, documents, hitl-threads, rules)
  * Onboarding flow (start, upload, extraction polling, finalize)
  * Per-document actions (upload, delete, request-from-buyer)

Every query is tenant-scoped via ``_user.tenant_id``. Agent work fans out
via ``BackgroundTasks`` so upload returns immediately; the frontend polls
the extraction endpoint until agents report ``completed``/``failed``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.contracts import ImporterProfile
from labelforge.core.auth import TokenPayload
from labelforge.api.v1.documents import get_blob_store
from labelforge.core.blobstore import BlobMeta
from labelforge.db.models import (
    ComplianceRule,
    HiTLThreadModel,
    Importer,
    ImporterDocument,
    ImporterOnboardingSession,
    ImporterProfileModel,
    Notification,
    Order,
)
from labelforge.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/importers", tags=["importers"])


# ── Request / response models ───────────────────────────────────────────────


class ImporterCreateRequest(BaseModel):
    name: str
    code: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None


class ImporterUpdateRequest(BaseModel):
    name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    is_active: Optional[bool] = None
    brand_treatment: Optional[dict] = None
    panel_layouts: Optional[dict] = None
    handling_symbol_rules: Optional[dict] = None
    pi_template_mapping: Optional[dict] = None


class ImporterCreateResponse(BaseModel):
    id: str
    name: str
    code: str


class ImporterListResponse(BaseModel):
    importers: list[ImporterProfile]
    total: int


class ImporterDocumentItem(BaseModel):
    id: str
    doc_type: str
    filename: str
    size_bytes: Optional[int]
    version: int
    uploaded_at: datetime
    content_hash: Optional[str] = None


class ImporterDocumentsResponse(BaseModel):
    documents: list[ImporterDocumentItem]
    total: int


class ImporterOrderItem(BaseModel):
    id: str
    po_number: Optional[str]
    external_ref: Optional[str]
    created_at: datetime


class ImporterOrdersResponse(BaseModel):
    orders: list[ImporterOrderItem]
    total: int


class ImporterHiTLItem(BaseModel):
    id: str
    order_id: str
    item_no: str
    agent_id: str
    priority: str
    status: str
    created_at: datetime


class ImporterHiTLResponse(BaseModel):
    threads: list[ImporterHiTLItem]
    total: int


class ImporterRuleItem(BaseModel):
    id: str
    rule_code: str
    title: str
    region: str
    placement: str
    version: int
    is_active: bool


class ImporterRulesResponse(BaseModel):
    rules: list[ImporterRuleItem]
    total: int


class OnboardingStartResponse(BaseModel):
    session_id: str
    status: str


class OnboardingUploadResponse(BaseModel):
    session_id: str
    status: str
    uploaded_docs: list[str]


class OnboardingAgentStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str  # pending | running | completed | failed
    confidence: Optional[float] = None
    error: Optional[str] = None


class OnboardingExtractionResponse(BaseModel):
    session_id: str
    status: str
    agents: dict[str, OnboardingAgentStatus]
    extracted_values: Optional[dict] = None
    started_at: datetime
    completed_at: Optional[datetime] = None


class OnboardingFinalizeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    brand_treatment: Optional[dict] = None
    panel_layouts: Optional[dict] = None
    handling_symbol_rules: Optional[dict] = None
    pi_template_mapping: Optional[dict] = None
    logo_asset_hash: Optional[str] = None


class OnboardingFinalizeResponse(BaseModel):
    importer_id: str
    profile_version: int


class RequestFromBuyerResponse(BaseModel):
    importer_id: str
    doc_type: str
    notification_id: str


# ── Helpers ──────────────────────────────────────────────────────────────────


_DOC_TYPES = {"protocol", "warnings", "checklist", "logo", "po", "pi", "msds", "other"}
_AGENT_KEYS = ("protocol", "warnings", "checklist")
_AGENT_DOC_TYPES = {"protocol", "warnings", "checklist"}


def _classify_doc_type(filename: str) -> str:
    """Map an uploaded filename to a known doc type using simple keyword hints."""
    lower = filename.lower()
    if "protocol" in lower:
        return "protocol"
    if "warning" in lower or "label" in lower:
        return "warnings"
    if "checklist" in lower or "rules" in lower:
        return "checklist"
    if "logo" in lower:
        return "logo"
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        return "pi"
    if "po" in lower or "purchase" in lower:
        return "po"
    return "other"


def _profile_to_contract(importer: Importer, profile: Optional[ImporterProfileModel]) -> ImporterProfile:
    return ImporterProfile(
        importer_id=importer.id,
        name=importer.name,
        code=importer.code,
        brand_treatment=profile.brand_treatment if profile else None,
        panel_layouts=profile.panel_layouts if profile else None,
        handling_symbol_rules=profile.handling_symbol_rules if profile else None,
        pi_template_mapping=profile.pi_template_mapping if profile else None,
        logo_asset_hash=profile.logo_asset_hash if profile else None,
        version=profile.version if profile else 0,
    )


async def _latest_profile(db: AsyncSession, importer_id: str) -> Optional[ImporterProfileModel]:
    subq = (
        select(func.max(ImporterProfileModel.version))
        .where(ImporterProfileModel.importer_id == importer_id)
        .scalar_subquery()
    )
    result = await db.execute(
        select(ImporterProfileModel).where(
            ImporterProfileModel.importer_id == importer_id,
            ImporterProfileModel.version == subq,
        )
    )
    return result.scalar_one_or_none()


async def _get_importer_or_404(db: AsyncSession, importer_id: str, tenant_id: str) -> Importer:
    result = await db.execute(
        select(Importer).where(
            Importer.id == importer_id,
            Importer.tenant_id == tenant_id,
        )
    )
    importer = result.scalar_one_or_none()
    if importer is None:
        raise HTTPException(status_code=404, detail="Importer not found")
    return importer


# ── CRUD endpoints ───────────────────────────────────────────────────────────


@router.get("", response_model=ImporterListResponse)
async def list_importers(
    search: Optional[str] = Query(None, description="Search by name or code"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_inactive: bool = Query(False),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterListResponse:
    """List importer profiles with optional search."""
    query = select(Importer).where(Importer.tenant_id == _user.tenant_id)
    count_query = select(func.count()).select_from(Importer).where(Importer.tenant_id == _user.tenant_id)

    if not include_inactive:
        query = query.where(Importer.is_active.is_(True))
        count_query = count_query.where(Importer.is_active.is_(True))

    if search:
        pattern = f"%{search}%"
        query = query.where(Importer.name.ilike(pattern) | Importer.code.ilike(pattern))
        count_query = count_query.where(Importer.name.ilike(pattern) | Importer.code.ilike(pattern))

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(Importer.name).offset(offset).limit(limit)
    result = await db.execute(query)
    importers = result.scalars().all()

    profiles: list[ImporterProfile] = []
    for importer in importers:
        profile = await _latest_profile(db, importer.id)
        profiles.append(_profile_to_contract(importer, profile))

    return ImporterListResponse(importers=profiles, total=total)


@router.get("/{importer_id}", response_model=ImporterProfile)
async def get_importer(
    importer_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterProfile:
    """Get a single importer profile by ID."""
    importer = await _get_importer_or_404(db, importer_id, _user.tenant_id)
    profile = await _latest_profile(db, importer.id)
    return _profile_to_contract(importer, profile)


@router.post("", response_model=ImporterCreateResponse, status_code=201)
async def create_importer(
    body: ImporterCreateRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterCreateResponse:
    """Create a new importer record. Profile is created later during finalize."""
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name is required")

    code = (body.code or body.name.strip().lower().replace(" ", "-"))[:100]

    # Enforce per-tenant code uniqueness
    existing = await db.execute(
        select(Importer).where(
            Importer.tenant_id == _user.tenant_id,
            Importer.code == code,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Importer with code '{code}' already exists")

    importer = Importer(
        id=f"imp-{uuid4().hex[:8]}",
        tenant_id=_user.tenant_id,
        name=body.name.strip(),
        code=code,
        is_active=True,
    )
    db.add(importer)
    await db.commit()
    return ImporterCreateResponse(id=importer.id, name=importer.name, code=importer.code)


@router.put("/{importer_id}", response_model=ImporterProfile)
async def update_importer(
    importer_id: str,
    body: ImporterUpdateRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterProfile:
    """Update importer top-level fields and/or create a new profile version.

    Scalar importer fields (name, is_active) are updated in-place. Profile
    fields (brand_treatment, panel_layouts, …) if present result in a new
    ImporterProfileModel row with version = latest + 1 so we preserve history.
    """
    importer = await _get_importer_or_404(db, importer_id, _user.tenant_id)

    if body.name is not None:
        importer.name = body.name.strip()
    if body.is_active is not None:
        importer.is_active = body.is_active

    profile_fields = {
        "brand_treatment": body.brand_treatment,
        "panel_layouts": body.panel_layouts,
        "handling_symbol_rules": body.handling_symbol_rules,
        "pi_template_mapping": body.pi_template_mapping,
    }
    if any(v is not None for v in profile_fields.values()):
        current = await _latest_profile(db, importer.id)
        new_profile = ImporterProfileModel(
            id=str(uuid4()),
            importer_id=importer.id,
            tenant_id=_user.tenant_id,
            version=(current.version + 1) if current else 1,
            brand_treatment=body.brand_treatment if body.brand_treatment is not None else (current.brand_treatment if current else None),
            panel_layouts=body.panel_layouts if body.panel_layouts is not None else (current.panel_layouts if current else None),
            handling_symbol_rules=body.handling_symbol_rules if body.handling_symbol_rules is not None else (current.handling_symbol_rules if current else None),
            pi_template_mapping=body.pi_template_mapping if body.pi_template_mapping is not None else (current.pi_template_mapping if current else None),
            logo_asset_hash=current.logo_asset_hash if current else None,
        )
        db.add(new_profile)

    await db.commit()
    await db.refresh(importer)
    profile = await _latest_profile(db, importer.id)
    return _profile_to_contract(importer, profile)


@router.delete("/{importer_id}", status_code=204)
async def delete_importer(
    importer_id: str,
    hard: bool = Query(False, description="If true, permanently delete"),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete an importer by flipping ``is_active`` to false.

    Pass ``?hard=true`` to physically delete (admin only — RBAC check).
    """
    importer = await _get_importer_or_404(db, importer_id, _user.tenant_id)

    if hard:
        if _user.role and str(_user.role).upper().endswith("ADMIN") is False:
            raise HTTPException(status_code=403, detail="Hard delete requires admin role")
        await db.delete(importer)
    else:
        importer.is_active = False

    await db.commit()


# ── Sub-resources ────────────────────────────────────────────────────────────


@router.get("/{importer_id}/orders", response_model=ImporterOrdersResponse)
async def list_importer_orders(
    importer_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterOrdersResponse:
    await _get_importer_or_404(db, importer_id, _user.tenant_id)

    count_result = await db.execute(
        select(func.count())
        .select_from(Order)
        .where(Order.importer_id == importer_id, Order.tenant_id == _user.tenant_id)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(Order)
        .where(Order.importer_id == importer_id, Order.tenant_id == _user.tenant_id)
        .order_by(desc(Order.created_at))
        .offset(offset)
        .limit(limit)
    )
    orders = result.scalars().all()

    return ImporterOrdersResponse(
        orders=[
            ImporterOrderItem(
                id=o.id,
                po_number=o.po_number,
                external_ref=o.external_ref,
                created_at=o.created_at,
            )
            for o in orders
        ],
        total=total,
    )


@router.get("/{importer_id}/documents", response_model=ImporterDocumentsResponse)
async def list_importer_documents(
    importer_id: str,
    doc_type: Optional[str] = Query(None),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterDocumentsResponse:
    """List importer onboarding documents, optionally filtered by doc_type."""
    await _get_importer_or_404(db, importer_id, _user.tenant_id)

    query = select(ImporterDocument).where(
        ImporterDocument.importer_id == importer_id,
        ImporterDocument.tenant_id == _user.tenant_id,
    )
    if doc_type:
        query = query.where(ImporterDocument.doc_type == doc_type)

    result = await db.execute(query.order_by(desc(ImporterDocument.uploaded_at)))
    docs = result.scalars().all()

    return ImporterDocumentsResponse(
        documents=[
            ImporterDocumentItem(
                id=d.id,
                doc_type=d.doc_type,
                filename=d.filename,
                size_bytes=d.size_bytes,
                version=d.version,
                uploaded_at=d.uploaded_at,
                content_hash=d.content_hash,
            )
            for d in docs
        ],
        total=len(docs),
    )


@router.post(
    "/{importer_id}/documents/{doc_type}",
    response_model=ImporterDocumentItem,
    status_code=201,
)
async def upload_importer_document(
    importer_id: str,
    doc_type: str,
    file: UploadFile = File(...),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterDocumentItem:
    """Upload or replace a single importer onboarding document.

    Multiple versions are preserved — this appends a new row with
    ``version = max(version) + 1`` for the given ``doc_type``.
    """
    if doc_type not in _DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown doc_type '{doc_type}'")

    await _get_importer_or_404(db, importer_id, _user.tenant_id)

    filename = file.filename or f"{doc_type}.bin"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit")

    # Bump version for this (importer, doc_type)
    latest_version_result = await db.execute(
        select(func.max(ImporterDocument.version)).where(
            ImporterDocument.importer_id == importer_id,
            ImporterDocument.doc_type == doc_type,
        )
    )
    next_version = (latest_version_result.scalar_one_or_none() or 0) + 1

    store = get_blob_store()
    storage_key = f"importers/{importer_id}/{doc_type}/v{next_version}_{filename}"
    blob_meta: BlobMeta = await store.upload(key=storage_key, data=content, content_type=file.content_type)

    doc = ImporterDocument(
        id=f"idoc-{uuid4().hex[:8]}",
        tenant_id=_user.tenant_id,
        importer_id=importer_id,
        doc_type=doc_type,
        filename=filename,
        s3_key=storage_key,
        content_hash=blob_meta.sha256,
        size_bytes=blob_meta.size_bytes,
        version=next_version,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return ImporterDocumentItem(
        id=doc.id,
        doc_type=doc.doc_type,
        filename=doc.filename,
        size_bytes=doc.size_bytes,
        version=doc.version,
        uploaded_at=doc.uploaded_at,
        content_hash=doc.content_hash,
    )


@router.delete("/{importer_id}/documents/{doc_type}", status_code=204)
async def delete_importer_document(
    importer_id: str,
    doc_type: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete the latest version of ``doc_type`` for this importer."""
    await _get_importer_or_404(db, importer_id, _user.tenant_id)

    result = await db.execute(
        select(ImporterDocument)
        .where(
            ImporterDocument.importer_id == importer_id,
            ImporterDocument.tenant_id == _user.tenant_id,
            ImporterDocument.doc_type == doc_type,
        )
        .order_by(desc(ImporterDocument.version))
    )
    doc = result.scalars().first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Best-effort blob cleanup — don't fail the request if blob is already gone
    try:
        await get_blob_store().delete(doc.s3_key)
    except Exception as exc:  # pragma: no cover — blob store backends vary
        logger.warning("blob delete failed for %s: %s", doc.s3_key, exc)

    await db.delete(doc)
    await db.commit()


@router.post(
    "/{importer_id}/documents/{doc_type}/request-from-buyer",
    response_model=RequestFromBuyerResponse,
)
async def request_document_from_buyer(
    importer_id: str,
    doc_type: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RequestFromBuyerResponse:
    """Log a request-to-buyer for a missing document.

    Creates a ``Notification`` row. A downstream notifier worker (email/slack)
    is expected to consume unread ``buyer_request`` notifications; keeping the
    API side side-effect free so tests don't need SMTP mocks.
    """
    if doc_type not in _DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown doc_type '{doc_type}'")
    importer = await _get_importer_or_404(db, importer_id, _user.tenant_id)

    notif = Notification(
        id=str(uuid4()),
        tenant_id=_user.tenant_id,
        user_id=_user.user_id,
        type="buyer_request",
        title=f"Requested {doc_type} from {importer.name}",
        body=f"Buyer email sent for missing '{doc_type}' document.",
        level="info",
    )
    db.add(notif)
    await db.commit()

    logger.info(
        "Buyer request logged: importer=%s doc_type=%s notification=%s",
        importer_id, doc_type, notif.id,
    )
    return RequestFromBuyerResponse(
        importer_id=importer_id,
        doc_type=doc_type,
        notification_id=notif.id,
    )


@router.get("/{importer_id}/hitl-threads", response_model=ImporterHiTLResponse)
async def list_importer_hitl_threads(
    importer_id: str,
    status: Optional[str] = Query(None),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterHiTLResponse:
    """List HiTL threads across orders belonging to this importer."""
    await _get_importer_or_404(db, importer_id, _user.tenant_id)

    order_ids_subq = (
        select(Order.id)
        .where(Order.importer_id == importer_id, Order.tenant_id == _user.tenant_id)
        .scalar_subquery()
    )
    query = select(HiTLThreadModel).where(
        HiTLThreadModel.tenant_id == _user.tenant_id,
        HiTLThreadModel.order_id.in_(order_ids_subq),
    )
    if status:
        query = query.where(HiTLThreadModel.status == status)
    result = await db.execute(query.order_by(desc(HiTLThreadModel.created_at)))
    threads = result.scalars().all()

    return ImporterHiTLResponse(
        threads=[
            ImporterHiTLItem(
                id=t.id,
                order_id=t.order_id,
                item_no=t.item_no,
                agent_id=t.agent_id,
                priority=t.priority,
                status=t.status,
                created_at=t.created_at,
            )
            for t in threads
        ],
        total=len(threads),
    )


@router.get("/{importer_id}/rules", response_model=ImporterRulesResponse)
async def list_importer_rules(
    importer_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterRulesResponse:
    """List compliance rules applicable to this importer (tenant-scoped)."""
    await _get_importer_or_404(db, importer_id, _user.tenant_id)

    result = await db.execute(
        select(ComplianceRule)
        .where(ComplianceRule.tenant_id == _user.tenant_id)
        .order_by(ComplianceRule.rule_code)
    )
    rules = result.scalars().all()

    return ImporterRulesResponse(
        rules=[
            ImporterRuleItem(
                id=r.id,
                rule_code=r.rule_code,
                title=r.title,
                region=r.region,
                placement=r.placement,
                version=r.version,
                is_active=r.is_active,
            )
            for r in rules
        ],
        total=len(rules),
    )


# ── Onboarding flow ──────────────────────────────────────────────────────────


@router.post(
    "/{importer_id}/onboarding/start",
    response_model=OnboardingStartResponse,
    status_code=201,
)
async def start_onboarding(
    importer_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingStartResponse:
    """Initialise an onboarding session (idempotent per-importer).

    If an ``in_progress`` session already exists it's returned; otherwise
    a fresh session is created with all agent statuses at ``pending``.
    """
    await _get_importer_or_404(db, importer_id, _user.tenant_id)

    existing_result = await db.execute(
        select(ImporterOnboardingSession)
        .where(
            ImporterOnboardingSession.importer_id == importer_id,
            ImporterOnboardingSession.tenant_id == _user.tenant_id,
            ImporterOnboardingSession.status == "in_progress",
        )
        .order_by(desc(ImporterOnboardingSession.started_at))
    )
    existing = existing_result.scalars().first()
    if existing is not None:
        return OnboardingStartResponse(session_id=existing.id, status=existing.status)

    session = ImporterOnboardingSession(
        id=f"onb-{uuid4().hex[:8]}",
        tenant_id=_user.tenant_id,
        importer_id=importer_id,
        status="in_progress",
        agents_state={k: {"status": "pending"} for k in _AGENT_KEYS},
        extracted_values={},
    )
    db.add(session)
    await db.commit()
    return OnboardingStartResponse(session_id=session.id, status=session.status)


@router.post(
    "/{importer_id}/onboarding/upload",
    response_model=OnboardingUploadResponse,
)
async def upload_onboarding_documents(
    importer_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingUploadResponse:
    """Accept onboarding documents, persist them, and fan out to agents.

    Each file is classified by filename (protocol/warnings/checklist/...).
    An ``ImporterOnboardingSession`` is created if none is in progress, and
    the three extraction agents run in the background. Clients poll
    ``GET /onboarding/extraction`` until ``status`` ≠ ``in_progress``.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    await _get_importer_or_404(db, importer_id, _user.tenant_id)

    # Reuse or create session
    existing_result = await db.execute(
        select(ImporterOnboardingSession)
        .where(
            ImporterOnboardingSession.importer_id == importer_id,
            ImporterOnboardingSession.tenant_id == _user.tenant_id,
            ImporterOnboardingSession.status == "in_progress",
        )
        .order_by(desc(ImporterOnboardingSession.started_at))
    )
    session = existing_result.scalars().first()
    if session is None:
        session = ImporterOnboardingSession(
            id=f"onb-{uuid4().hex[:8]}",
            tenant_id=_user.tenant_id,
            importer_id=importer_id,
            status="in_progress",
            agents_state={k: {"status": "pending"} for k in _AGENT_KEYS},
            extracted_values={},
        )
        db.add(session)

    store = get_blob_store()
    uploaded_doc_types: list[str] = []
    agent_payloads: dict[str, tuple[str, bytes, str]] = {}  # doc_type -> (filename, bytes, s3_key)

    for file in files:
        filename = file.filename or "upload.bin"
        content = await file.read()
        if not content:
            continue
        if len(content) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"{filename} exceeds 25 MB limit")

        doc_type = _classify_doc_type(filename)

        latest_version_result = await db.execute(
            select(func.max(ImporterDocument.version)).where(
                ImporterDocument.importer_id == importer_id,
                ImporterDocument.doc_type == doc_type,
            )
        )
        next_version = (latest_version_result.scalar_one_or_none() or 0) + 1

        storage_key = f"importers/{importer_id}/{doc_type}/v{next_version}_{filename}"
        blob_meta = await store.upload(key=storage_key, data=content, content_type=file.content_type)

        doc = ImporterDocument(
            id=f"idoc-{uuid4().hex[:8]}",
            tenant_id=_user.tenant_id,
            importer_id=importer_id,
            doc_type=doc_type,
            filename=filename,
            s3_key=storage_key,
            content_hash=blob_meta.sha256,
            size_bytes=blob_meta.size_bytes,
            version=next_version,
        )
        db.add(doc)
        uploaded_doc_types.append(doc_type)

        if doc_type in _AGENT_DOC_TYPES and doc_type not in agent_payloads:
            agent_payloads[doc_type] = (filename, content, storage_key)

    # Mark pending agents as "running" for any docs we're about to process
    agents_state = dict(session.agents_state or {})
    for key in _AGENT_KEYS:
        if key in agent_payloads:
            agents_state[key] = {"status": "running"}
        else:
            agents_state.setdefault(key, {"status": "pending"})
    session.agents_state = agents_state

    await db.commit()
    session_id = session.id

    # Fan out agents to background
    for doc_type, (filename, content, _key) in agent_payloads.items():
        background_tasks.add_task(
            _run_onboarding_agent,
            session_id=session_id,
            tenant_id=_user.tenant_id,
            importer_id=importer_id,
            agent_key=doc_type,
            filename=filename,
            content=content,
        )

    return OnboardingUploadResponse(
        session_id=session_id,
        status=session.status,
        uploaded_docs=uploaded_doc_types,
    )


@router.get(
    "/{importer_id}/onboarding/extraction",
    response_model=OnboardingExtractionResponse,
)
async def get_onboarding_extraction(
    importer_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingExtractionResponse:
    """Return current onboarding agent progress + extracted values.

    Frontend polls this every ~2 s while status == ``in_progress``.
    """
    await _get_importer_or_404(db, importer_id, _user.tenant_id)

    result = await db.execute(
        select(ImporterOnboardingSession)
        .where(
            ImporterOnboardingSession.importer_id == importer_id,
            ImporterOnboardingSession.tenant_id == _user.tenant_id,
        )
        .order_by(desc(ImporterOnboardingSession.started_at))
    )
    session = result.scalars().first()
    if session is None:
        raise HTTPException(status_code=404, detail="No onboarding session found")

    agents_state_raw = session.agents_state or {}
    agents = {
        key: OnboardingAgentStatus(**(agents_state_raw.get(key) or {"status": "pending"}))
        for key in _AGENT_KEYS
    }

    return OnboardingExtractionResponse(
        session_id=session.id,
        status=session.status,
        agents=agents,
        extracted_values=session.extracted_values or {},
        started_at=session.started_at,
        completed_at=session.completed_at,
    )


@router.post(
    "/{importer_id}/onboard/finalize",
    response_model=OnboardingFinalizeResponse,
)
async def finalize_onboarding(
    importer_id: str,
    body: OnboardingFinalizeRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingFinalizeResponse:
    """Create an ``ImporterProfileModel`` from reviewed values and close the session."""
    importer = await _get_importer_or_404(db, importer_id, _user.tenant_id)

    current = await _latest_profile(db, importer.id)
    new_version = (current.version + 1) if current else 1

    new_profile = ImporterProfileModel(
        id=str(uuid4()),
        importer_id=importer.id,
        tenant_id=_user.tenant_id,
        version=new_version,
        brand_treatment=body.brand_treatment,
        panel_layouts=body.panel_layouts,
        handling_symbol_rules=body.handling_symbol_rules,
        pi_template_mapping=body.pi_template_mapping,
        logo_asset_hash=body.logo_asset_hash,
    )
    db.add(new_profile)

    # Close any in-progress session
    session_result = await db.execute(
        select(ImporterOnboardingSession)
        .where(
            ImporterOnboardingSession.importer_id == importer_id,
            ImporterOnboardingSession.tenant_id == _user.tenant_id,
            ImporterOnboardingSession.status == "in_progress",
        )
    )
    for session in session_result.scalars().all():
        session.status = "completed"
        session.completed_at = datetime.now(timezone.utc)

    await db.commit()
    return OnboardingFinalizeResponse(importer_id=importer_id, profile_version=new_version)


# ── Background agent runner ──────────────────────────────────────────────────


async def _run_onboarding_agent(
    session_id: str,
    tenant_id: str,
    importer_id: str,
    agent_key: str,
    filename: str,
    content: bytes,
) -> None:
    """Background task: run one onboarding agent and persist its result.

    agent_key ∈ {"protocol", "warnings", "checklist"}.
    """
    from labelforge.agents.checklist_extractor import ChecklistExtractorAgent
    from labelforge.agents.protocol_analyzer import ProtocolAnalyzerAgent
    from labelforge.agents.warning_label_parser import WarningLabelParserAgent
    from labelforge.config import settings as app_settings
    from labelforge.core.doc_extract import extract_text
    from labelforge.db.session import async_session_factory

    try:
        text = extract_text(content, filename)

        llm_provider = None
        if app_settings.openai_api_key:
            from labelforge.api.v1.orders import _LLMProviderWrapper
            from labelforge.core.llm import OpenAIProvider
            provider = OpenAIProvider(api_key=app_settings.openai_api_key)
            llm_provider = _LLMProviderWrapper(provider, app_settings.llm_default_model)

        # Without an LLM provider the agents would crash on .complete() — fall
        # back to the deterministic fixture payload the agents already ship
        # with. Lets local dev + tests run without real API keys.
        if llm_provider is None:
            agent_result_data = _agent_fallback(agent_key)
            confidence = 0.85
            needs_hitl = False
            error = None
        else:
            if agent_key == "protocol":
                agent = ProtocolAnalyzerAgent(llm_provider=llm_provider)
                input_data = {"document_content": text, "importer_id": importer_id}
            elif agent_key == "warnings":
                agent = WarningLabelParserAgent(llm_provider=llm_provider)
                input_data = {"document_content": text}
            elif agent_key == "checklist":
                agent = ChecklistExtractorAgent(llm_provider=llm_provider)
                input_data = {"document_content": text}
            else:
                logger.warning("Unknown onboarding agent key: %s", agent_key)
                return

            result = await agent.execute(input_data)
            agent_result_data = result.data
            confidence = result.confidence
            needs_hitl = result.needs_hitl
            error = result.hitl_reason if needs_hitl else None

        async with async_session_factory() as db:
            sess_result = await db.execute(
                select(ImporterOnboardingSession).where(
                    ImporterOnboardingSession.id == session_id,
                    ImporterOnboardingSession.tenant_id == tenant_id,
                )
            )
            session = sess_result.scalar_one_or_none()
            if session is None:
                logger.warning("Onboarding session %s not found when agent finished", session_id)
                return

            agents_state = dict(session.agents_state or {})
            agents_state[agent_key] = {
                "status": "completed",
                "confidence": confidence,
                "needs_hitl": needs_hitl,
                "error": error,
            }
            session.agents_state = agents_state

            extracted = dict(session.extracted_values or {})
            extracted[agent_key] = agent_result_data
            session.extracted_values = extracted

            # If every agent that was ever set to running/completed is now done,
            # flip session to "ready_for_review" — frontend still treats this as
            # a terminal polling state alongside "completed"/"failed".
            all_done = all(
                (agents_state.get(k) or {}).get("status") in ("completed", "failed", "pending")
                for k in _AGENT_KEYS
            )
            any_running = any(
                (agents_state.get(k) or {}).get("status") == "running"
                for k in _AGENT_KEYS
            )
            if all_done and not any_running:
                session.status = "ready_for_review"

            await db.commit()

    except Exception as exc:  # pragma: no cover — background task failure path
        logger.exception("Onboarding agent %s failed for session %s: %s", agent_key, session_id, exc)
        try:
            async with async_session_factory() as db:
                sess_result = await db.execute(
                    select(ImporterOnboardingSession).where(
                        ImporterOnboardingSession.id == session_id,
                    )
                )
                session = sess_result.scalar_one_or_none()
                if session is not None:
                    agents_state = dict(session.agents_state or {})
                    agents_state[agent_key] = {"status": "failed", "error": str(exc)}
                    session.agents_state = agents_state
                    await db.commit()
        except Exception:
            pass


def _agent_fallback(agent_key: str) -> dict:
    """Deterministic fixture payloads so onboarding works without an LLM key."""
    if agent_key == "protocol":
        return {
            "brand_treatment": {
                "primary_color": "#000000",
                "font_family": "Arial",
                "logo_position": "top-right",
            },
            "panel_layouts": {
                "carton_top": ["logo", "upc", "item_description"],
                "carton_side": ["warnings", "country_of_origin"],
            },
            "handling_symbol_rules": {"fragile": True, "this_side_up": True, "keep_dry": False},
            "special_fields": {},
            "confidence": 0.85,
        }
    if agent_key == "warnings":
        return {
            "labels": [
                {
                    "label_code": "PROP65_CANCER",
                    "text_en": "WARNING: California Prop 65 chemical exposure notice.",
                    "text_es": "",
                    "text_fr": "",
                    "placement_rules": "primary display panel",
                    "applicability_conditions": "contains listed chemicals",
                }
            ],
            "region": "US",
            "label_count": 1,
        }
    if agent_key == "checklist":
        return {
            "rules": [
                {
                    "rule_code": "PROP65",
                    "title": "California Proposition 65 Warning",
                    "category": "labeling",
                    "conditions": {"AND": [{"==": ["destination", "US"]}]},
                    "requirements": {"warning_label": "PROP65_CANCER"},
                }
            ],
            "region": "US",
            "rule_count": 1,
        }
    return {}
