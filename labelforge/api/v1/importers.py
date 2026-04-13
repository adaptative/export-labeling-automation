"""Importer profile and onboarding endpoints."""
from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.contracts import ImporterProfile
from labelforge.core.auth import TokenPayload
from labelforge.core.blobstore import MemoryBlobStore
from labelforge.db.models import Document, HiTLThreadModel, Importer, ImporterProfileModel, Order
from labelforge.db.session import get_db

router = APIRouter(prefix="/importers", tags=["importers"])

# ── In-memory stores for onboarding ────────────────────────────────────────

_extraction_results: dict[str, dict] = {}
_blob_store = MemoryBlobStore()


# ── Request / Response models ──────────────────────────────────────────────


class ImporterSummaryResponse(BaseModel):
    """Enriched importer summary matching frontend ImporterSummary interface."""
    id: str
    name: str
    code: str
    status: str
    countries: list[str] = []
    profile_version: int = 0
    onboarding_progress: int = 0
    orders_mtd: int = 0
    open_hitl: int = 0
    required_fields: list[str] = []
    # Detail-level fields (populated on GET /{id})
    buyer_contact: Optional[str] = None
    buyer_email: Optional[str] = None
    portal_token: Optional[str] = None
    since: Optional[str] = None
    label_languages: list[str] = []
    units: Optional[str] = None
    barcode_placement: Optional[str] = None
    panel_layout: Optional[str] = None
    brand_treatment: Optional[str] = None
    handling_symbol_rules: list[str] = []
    doc_requirements: list[str] = []
    notes: Optional[str] = None


class ImporterListResponse(BaseModel):
    importers: list[ImporterSummaryResponse]
    total: int


class ImporterCreateRequest(BaseModel):
    name: str
    code: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None


class ImporterUpdateRequest(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    is_active: Optional[bool] = None


class ImporterResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    code: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    is_active: bool


class UploadDocumentInfo(BaseModel):
    document_type: str
    blob_key: str
    size_bytes: int
    sha256: str


class OnboardingUploadResponse(BaseModel):
    importer_id: str
    status: str
    documents: list[UploadDocumentInfo]


class AgentExtractionResult(BaseModel):
    agent_id: str
    status: str
    confidence: float
    needs_hitl: bool
    hitl_reason: Optional[str] = None
    data: Optional[dict] = None


class ExtractionStatusResponse(BaseModel):
    importer_id: str
    status: str
    results: list[AgentExtractionResult]


class FinalizeOnboardingRequest(BaseModel):
    brand_treatment: Optional[dict] = None
    panel_layouts: Optional[dict] = None
    handling_symbol_rules: Optional[dict] = None
    warning_labels: Optional[dict] = None
    compliance_rules: Optional[dict] = None


class ImporterProfileResponse(BaseModel):
    id: str
    importer_id: str
    tenant_id: str
    version: int
    brand_treatment: Optional[dict] = None
    panel_layouts: Optional[dict] = None
    handling_symbol_rules: Optional[dict] = None
    pi_template_mapping: Optional[dict] = None
    logo_asset_hash: Optional[str] = None


class OrderSummary(BaseModel):
    id: str
    po_number: Optional[str] = None
    external_ref: Optional[str] = None
    notes: Optional[str] = None


class OrderListResponse(BaseModel):
    orders: list[OrderSummary]
    total: int


class DocumentSummary(BaseModel):
    id: str
    order_id: str
    filename: str
    s3_key: str
    size_bytes: Optional[int] = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentSummary]
    total: int


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _build_summary(
    importer: Importer,
    profile: Optional[ImporterProfileModel],
    db: AsyncSession,
    *,
    include_detail: bool = False,
) -> ImporterSummaryResponse:
    """Build enriched summary with computed stats."""
    # Determine status
    if not importer.is_active:
        status = "inactive"
    elif profile and profile.version >= 1:
        status = "active"
    else:
        status = "onboarding"

    # Compute onboarding progress based on profile fields
    if profile:
        filled = sum(1 for f in [
            profile.brand_treatment, profile.panel_layouts,
            profile.handling_symbol_rules, profile.pi_template_mapping,
            profile.logo_asset_hash,
        ] if f)
        onboarding_progress = min(100, int((filled / 5) * 100))
    else:
        onboarding_progress = 0

    # Count orders for this importer
    orders_result = await db.execute(
        select(func.count()).select_from(Order).where(
            Order.importer_id == importer.id,
            Order.tenant_id == importer.tenant_id,
        )
    )
    orders_mtd = orders_result.scalar_one()

    # Count open HiTL threads (via orders)
    order_ids_subq = select(Order.id).where(
        Order.importer_id == importer.id,
        Order.tenant_id == importer.tenant_id,
    ).scalar_subquery()
    hitl_result = await db.execute(
        select(func.count()).select_from(HiTLThreadModel).where(
            HiTLThreadModel.order_id.in_(
                select(Order.id).where(
                    Order.importer_id == importer.id,
                    Order.tenant_id == importer.tenant_id,
                )
            ),
            HiTLThreadModel.status.in_(["OPEN", "IN_PROGRESS"]),
        )
    )
    open_hitl = hitl_result.scalar_one()

    summary = ImporterSummaryResponse(
        id=importer.id,
        name=importer.name,
        code=importer.code,
        status=status,
        profile_version=profile.version if profile else 0,
        onboarding_progress=onboarding_progress,
        orders_mtd=orders_mtd,
        open_hitl=open_hitl,
    )

    if include_detail:
        summary.buyer_contact = importer.contact_phone
        summary.buyer_email = importer.contact_email
        summary.since = importer.created_at.isoformat() if importer.created_at else None
        summary.notes = importer.address
        if profile:
            bt = profile.brand_treatment
            summary.brand_treatment = bt.get("company_name", "") if bt else None
            pl = profile.panel_layouts
            summary.panel_layout = next(iter(pl.values()), None) if pl and isinstance(pl, dict) else None
            hs = profile.handling_symbol_rules
            summary.handling_symbol_rules = [k for k, v in hs.items() if v] if hs and isinstance(hs, dict) else []

    return summary


def _profile_to_contract(importer: Importer, profile: Optional[ImporterProfileModel]) -> ImporterProfile:
    return ImporterProfile(
        importer_id=importer.id,
        name=importer.name,
        code=importer.code,
        is_active=importer.is_active,
        brand_treatment=profile.brand_treatment if profile else None,
        panel_layouts=profile.panel_layouts if profile else None,
        handling_symbol_rules=profile.handling_symbol_rules if profile else None,
        pi_template_mapping=profile.pi_template_mapping if profile else None,
        logo_asset_hash=profile.logo_asset_hash if profile else None,
        version=profile.version if profile else 0,
    )


def _importer_to_response(importer: Importer) -> ImporterResponse:
    return ImporterResponse(
        id=importer.id,
        tenant_id=importer.tenant_id,
        name=importer.name,
        code=importer.code,
        contact_email=importer.contact_email,
        contact_phone=importer.contact_phone,
        address=importer.address,
        is_active=importer.is_active,
    )


async def _get_importer_or_404(
    importer_id: str, tenant_id: str, db: AsyncSession
) -> Importer:
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


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=ImporterListResponse)
async def list_importers(
    search: Optional[str] = Query(None, description="Search by importer ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterListResponse:
    """List importer profiles with optional search."""
    query = select(Importer).where(Importer.tenant_id == _user.tenant_id)
    count_query = select(func.count()).select_from(Importer).where(Importer.tenant_id == _user.tenant_id)

    if search:
        pattern = f"%{search}%"
        query = query.where(Importer.name.ilike(pattern) | Importer.code.ilike(pattern))
        count_query = count_query.where(Importer.name.ilike(pattern) | Importer.code.ilike(pattern))

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(Importer.name).offset(offset).limit(limit)
    result = await db.execute(query)
    importers = result.scalars().all()

    summaries: list[ImporterSummaryResponse] = []
    for importer in importers:
        # Get latest profile (highest version) for each importer
        subq = (
            select(func.max(ImporterProfileModel.version))
            .where(ImporterProfileModel.importer_id == importer.id)
            .scalar_subquery()
        )
        prof_result = await db.execute(
            select(ImporterProfileModel).where(
                ImporterProfileModel.importer_id == importer.id,
                ImporterProfileModel.version == subq,
            )
        )
        profile = prof_result.scalar_one_or_none()
        summaries.append(await _build_summary(importer, profile, db))

    return ImporterListResponse(importers=summaries, total=total)


@router.post("", response_model=ImporterResponse, status_code=201)
async def create_importer(
    body: ImporterCreateRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterResponse:
    """Create a new importer."""
    importer = Importer(
        id=str(uuid4()),
        tenant_id=_user.tenant_id,
        name=body.name,
        code=body.code,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
        address=body.address,
    )
    db.add(importer)
    await db.commit()
    await db.refresh(importer)
    return _importer_to_response(importer)


@router.get("/{importer_id}", response_model=ImporterSummaryResponse)
async def get_importer(
    importer_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterSummaryResponse:
    """Get a single importer profile by ID with computed stats."""
    importer = await _get_importer_or_404(importer_id, _user.tenant_id, db)

    # Get latest profile
    subq = (
        select(func.max(ImporterProfileModel.version))
        .where(ImporterProfileModel.importer_id == importer.id)
        .scalar_subquery()
    )
    prof_result = await db.execute(
        select(ImporterProfileModel).where(
            ImporterProfileModel.importer_id == importer.id,
            ImporterProfileModel.version == subq,
        )
    )
    profile = prof_result.scalar_one_or_none()

    return await _build_summary(importer, profile, db, include_detail=True)


@router.put("/{importer_id}", response_model=ImporterResponse)
async def update_importer(
    importer_id: str,
    body: ImporterUpdateRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterResponse:
    """Update an existing importer."""
    importer = await _get_importer_or_404(importer_id, _user.tenant_id, db)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(importer, field, value)

    await db.commit()
    await db.refresh(importer)
    return _importer_to_response(importer)


@router.delete("/{importer_id}", status_code=200)
async def delete_importer(
    importer_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Soft-delete an importer by setting is_active=False."""
    importer = await _get_importer_or_404(importer_id, _user.tenant_id, db)
    importer.is_active = False
    await db.commit()
    return {"detail": "Importer deactivated", "id": importer_id}


@router.post("/{importer_id}/onboarding/upload", response_model=OnboardingUploadResponse)
async def upload_onboarding_documents(
    importer_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    protocol: Optional[UploadFile] = File(None),
    warnings: Optional[UploadFile] = File(None),
    checklist: Optional[UploadFile] = File(None),
) -> OnboardingUploadResponse:
    """Upload onboarding documents and trigger agent extraction."""
    importer = await _get_importer_or_404(importer_id, _user.tenant_id, db)

    files = {
        "protocol": protocol,
        "warnings": warnings,
        "checklist": checklist,
    }

    uploaded_docs: list[UploadDocumentInfo] = []
    file_contents: dict[str, bytes] = {}

    for doc_type, upload_file in files.items():
        if upload_file is None:
            continue
        content = await upload_file.read()
        blob_key = f"onboarding/{importer_id}/{doc_type}/{upload_file.filename}"
        meta = await _blob_store.upload(blob_key, content, content_type="application/pdf")
        file_contents[doc_type] = content
        uploaded_docs.append(
            UploadDocumentInfo(
                document_type=doc_type,
                blob_key=blob_key,
                size_bytes=meta.size_bytes,
                sha256=meta.sha256,
            )
        )

    # Run agents synchronously (dev mode with StubLLMProvider)
    from tests.stubs import StubLLMProvider

    llm = StubLLMProvider()
    agent_results: dict[str, dict] = {}

    if "protocol" in file_contents:
        from labelforge.agents.protocol_analyzer import ProtocolAnalyzerAgent

        agent = ProtocolAnalyzerAgent(llm)
        result = await agent.execute(
            {"document_content": file_contents["protocol"].decode("utf-8", errors="replace"), "importer_id": importer_id}
        )
        agent_results["protocol_analyzer"] = {
            "agent_id": agent.agent_id,
            "status": "completed",
            "confidence": result.confidence,
            "needs_hitl": result.needs_hitl,
            "hitl_reason": result.hitl_reason,
            "data": result.data,
        }

    if "warnings" in file_contents:
        from labelforge.agents.warning_label_parser import WarningLabelParserAgent

        agent = WarningLabelParserAgent(llm)
        result = await agent.execute(
            {"document_content": file_contents["warnings"].decode("utf-8", errors="replace")}
        )
        agent_results["warning_label_parser"] = {
            "agent_id": agent.agent_id,
            "status": "completed",
            "confidence": result.confidence,
            "needs_hitl": result.needs_hitl,
            "hitl_reason": result.hitl_reason,
            "data": result.data,
        }

    if "checklist" in file_contents:
        from labelforge.agents.checklist_extractor import ChecklistExtractorAgent

        agent = ChecklistExtractorAgent(llm)
        result = await agent.execute(
            {"document_content": file_contents["checklist"].decode("utf-8", errors="replace")}
        )
        agent_results["checklist_extractor"] = {
            "agent_id": agent.agent_id,
            "status": "completed",
            "confidence": result.confidence,
            "needs_hitl": result.needs_hitl,
            "hitl_reason": result.hitl_reason,
            "data": result.data,
        }

    _extraction_results[importer_id] = agent_results

    return OnboardingUploadResponse(
        importer_id=importer_id,
        status="processing_complete",
        documents=uploaded_docs,
    )


@router.get("/{importer_id}/onboarding/extraction", response_model=ExtractionStatusResponse)
async def get_extraction_status(
    importer_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExtractionStatusResponse:
    """Get the extraction results from onboarding agents."""
    await _get_importer_or_404(importer_id, _user.tenant_id, db)

    agent_results = _extraction_results.get(importer_id, {})

    if not agent_results:
        return ExtractionStatusResponse(
            importer_id=importer_id,
            status="no_results",
            results=[],
        )

    results = [
        AgentExtractionResult(
            agent_id=r["agent_id"],
            status=r["status"],
            confidence=r["confidence"],
            needs_hitl=r["needs_hitl"],
            hitl_reason=r.get("hitl_reason"),
            data=r.get("data"),
        )
        for r in agent_results.values()
    ]

    overall_status = "completed"
    if any(r.needs_hitl for r in results):
        overall_status = "needs_review"

    return ExtractionStatusResponse(
        importer_id=importer_id,
        status=overall_status,
        results=results,
    )


@router.post("/{importer_id}/onboard/finalize", response_model=ImporterProfileResponse, status_code=201)
async def finalize_onboarding(
    importer_id: str,
    body: FinalizeOnboardingRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImporterProfileResponse:
    """Finalize onboarding by creating a new ImporterProfile version."""
    importer = await _get_importer_or_404(importer_id, _user.tenant_id, db)

    # Determine the next version number
    max_version_result = await db.execute(
        select(func.max(ImporterProfileModel.version)).where(
            ImporterProfileModel.importer_id == importer_id
        )
    )
    max_version = max_version_result.scalar_one_or_none() or 0
    next_version = max_version + 1

    profile = ImporterProfileModel(
        id=str(uuid4()),
        importer_id=importer_id,
        tenant_id=_user.tenant_id,
        version=next_version,
        brand_treatment=body.brand_treatment,
        panel_layouts=body.panel_layouts,
        handling_symbol_rules=body.handling_symbol_rules,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    return ImporterProfileResponse(
        id=profile.id,
        importer_id=profile.importer_id,
        tenant_id=profile.tenant_id,
        version=profile.version,
        brand_treatment=profile.brand_treatment,
        panel_layouts=profile.panel_layouts,
        handling_symbol_rules=profile.handling_symbol_rules,
        pi_template_mapping=profile.pi_template_mapping,
        logo_asset_hash=profile.logo_asset_hash,
    )


@router.get("/{importer_id}/orders", response_model=OrderListResponse)
async def list_importer_orders(
    importer_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderListResponse:
    """List orders for this importer."""
    await _get_importer_or_404(importer_id, _user.tenant_id, db)

    count_query = (
        select(func.count())
        .select_from(Order)
        .where(Order.importer_id == importer_id, Order.tenant_id == _user.tenant_id)
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = (
        select(Order)
        .where(Order.importer_id == importer_id, Order.tenant_id == _user.tenant_id)
        .order_by(desc(Order.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    orders = result.scalars().all()

    return OrderListResponse(
        orders=[
            OrderSummary(
                id=o.id,
                po_number=o.po_number,
                external_ref=o.external_ref,
                notes=o.notes,
            )
            for o in orders
        ],
        total=total,
    )


@router.get("/{importer_id}/documents", response_model=DocumentListResponse)
async def list_importer_documents(
    importer_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    """List documents for this importer (via associated orders)."""
    await _get_importer_or_404(importer_id, _user.tenant_id, db)

    # Get order IDs for this importer
    order_ids_query = select(Order.id).where(
        Order.importer_id == importer_id,
        Order.tenant_id == _user.tenant_id,
    )

    count_query = (
        select(func.count())
        .select_from(Document)
        .where(
            Document.order_id.in_(order_ids_query),
            Document.tenant_id == _user.tenant_id,
        )
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = (
        select(Document)
        .where(
            Document.order_id.in_(order_ids_query),
            Document.tenant_id == _user.tenant_id,
        )
        .order_by(desc(Document.uploaded_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    docs = result.scalars().all()

    return DocumentListResponse(
        documents=[
            DocumentSummary(
                id=d.id,
                order_id=d.order_id,
                filename=d.filename,
                s3_key=d.s3_key,
                size_bytes=d.size_bytes,
            )
            for d in docs
        ],
        total=total,
    )
