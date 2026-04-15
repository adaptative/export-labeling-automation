"""Warning-label library endpoints.

INT-011 (Sprint 10) adds full CRUD plus a pending → approved/rejected
approval workflow on top of the list/get routes that already existed.
Route map::

    GET    /warning-labels              — list with filters + search
    GET    /warning-labels/{id}         — single label
    POST   /warning-labels              — create (starts ``pending``)
    PUT    /warning-labels/{id}         — update text/metadata
    POST   /warning-labels/{id}/approve — mark approved + activate
    POST   /warning-labels/{id}/reject  — mark rejected + deactivate
    POST   /warning-labels/{id}/deprecate — retire an approved label

Approval semantics mirror the rule-management lifecycle: the ``name``
(``code``) is immutable once a label has been approved — regulatory
wording is owned by Legal and we refuse to silently rewrite history.
Every mutation is tagged with ``created_by`` / ``approved_by`` for
audit.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.core.auth import Capability, ROLE_CAPABILITIES, TokenPayload
from labelforge.db.models import WarningLabel as WarningLabelModel
from labelforge.db.session import get_db

router = APIRouter(prefix="/warning-labels", tags=["warning-labels"])


# ── Allowed values ──────────────────────────────────────────────────────────

_STATUS_PENDING = "pending"
_STATUS_APPROVED = "approved"
_STATUS_REJECTED = "rejected"
_STATUS_DEPRECATED = "deprecated"
_ALLOWED_STATUSES = {
    _STATUS_PENDING,
    _STATUS_APPROVED,
    _STATUS_REJECTED,
    _STATUS_DEPRECATED,
}


# ── Response models ──────────────────────────────────────────────────────────


class WarningLabel(BaseModel):
    id: str
    code: str
    title: str
    text: str
    text_es: Optional[str] = None
    text_fr: Optional[str] = None
    region: str
    placement: str
    status: str
    active: bool
    size_mm_width: Optional[int] = None
    size_mm_height: Optional[int] = None
    trigger_conditions: Optional[dict] = None
    variants: Optional[list[dict]] = None
    icon_asset_hash: Optional[str] = None
    created_by: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejected_reason: Optional[str] = None
    updated_at: datetime


class WarningLabelListResponse(BaseModel):
    warning_labels: list[WarningLabel]
    total: int


# ── Request models ──────────────────────────────────────────────────────────


class WarningLabelCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=500)
    text: str = Field(..., min_length=1)
    text_es: Optional[str] = None
    text_fr: Optional[str] = None
    region: str = "US"
    placement: str = "both"
    size_mm_width: Optional[int] = Field(None, ge=1, le=1000)
    size_mm_height: Optional[int] = Field(None, ge=1, le=1000)
    trigger_conditions: Optional[dict] = None
    variants: Optional[list[dict]] = None
    icon_asset_hash: Optional[str] = None


class WarningLabelUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    text: Optional[str] = Field(None, min_length=1)
    text_es: Optional[str] = None
    text_fr: Optional[str] = None
    region: Optional[str] = None
    placement: Optional[str] = None
    size_mm_width: Optional[int] = Field(None, ge=1, le=1000)
    size_mm_height: Optional[int] = Field(None, ge=1, le=1000)
    trigger_conditions: Optional[dict] = None
    variants: Optional[list[dict]] = None
    icon_asset_hash: Optional[str] = None


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _ensure_capability(user: TokenPayload, cap: Capability) -> None:
    role_caps = ROLE_CAPABILITIES.get(user.role, set())
    if cap in role_caps or cap in user.capabilities:
        return
    raise HTTPException(status_code=403, detail=f"Missing capability: {cap.value}")


def _variants_to_list(raw: Any) -> Optional[list[dict]]:
    """The ``variants`` column is stored as JSON — normalise to a list of dicts."""
    if raw is None:
        return None
    if isinstance(raw, list):
        return [v for v in raw if isinstance(v, dict)]
    # Older rows may have persisted the payload as a dict keyed by language code.
    if isinstance(raw, dict):
        return [{"language": k, **(v if isinstance(v, dict) else {"text": v})}
                for k, v in raw.items()]
    return None


def _model_to_response(w: WarningLabelModel) -> WarningLabel:
    return WarningLabel(
        id=w.id,
        code=w.code,
        title=w.title,
        text=w.text_en,
        text_es=w.text_es,
        text_fr=w.text_fr,
        region=w.region,
        placement=w.placement,
        status=w.status,
        active=w.is_active,
        size_mm_width=w.size_mm_width,
        size_mm_height=w.size_mm_height,
        trigger_conditions=w.trigger_conditions,
        variants=_variants_to_list(w.variants),
        icon_asset_hash=w.icon_asset_hash,
        created_by=w.created_by,
        approved_by=w.approved_by,
        approved_at=w.approved_at,
        rejected_reason=w.rejected_reason,
        updated_at=w.updated_at or w.created_at,
    )


async def _get_label(
    db: AsyncSession, tenant_id: str, label_id: str
) -> WarningLabelModel:
    result = await db.execute(
        select(WarningLabelModel).where(
            WarningLabelModel.id == label_id,
            WarningLabelModel.tenant_id == tenant_id,
        )
    )
    label = result.scalar_one_or_none()
    if label is None:
        raise HTTPException(status_code=404, detail="Warning label not found")
    return label


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=WarningLabelListResponse)
async def list_warning_labels(
    region: Optional[str] = Query(None, description="Filter by region (e.g. US, US-CA, EU)"),
    placement: Optional[str] = Query(
        None, description="Filter by placement: carton, product, both, hangtag"
    ),
    code: Optional[str] = Query(None, description="Filter by warning code"),
    status: Optional[str] = Query(
        None, description="Filter by status: pending, approved, rejected, deprecated"
    ),
    active: Optional[bool] = Query(None, description="Filter by active flag"),
    search: Optional[str] = Query(
        None, description="Full-text search across title / regulatory text / code"
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WarningLabelListResponse:
    """List warning labels with filters + search."""
    base = select(WarningLabelModel).where(
        WarningLabelModel.tenant_id == _user.tenant_id
    )
    count_q = select(func.count()).select_from(WarningLabelModel).where(
        WarningLabelModel.tenant_id == _user.tenant_id
    )

    def _apply(q, col, value):
        if value is not None:
            q = q.where(col == value)
        return q

    base = _apply(base, WarningLabelModel.region, region)
    count_q = _apply(count_q, WarningLabelModel.region, region)
    base = _apply(base, WarningLabelModel.placement, placement)
    count_q = _apply(count_q, WarningLabelModel.placement, placement)
    base = _apply(base, WarningLabelModel.code, code)
    count_q = _apply(count_q, WarningLabelModel.code, code)
    if status is not None:
        if status not in _ALLOWED_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        base = base.where(WarningLabelModel.status == status)
        count_q = count_q.where(WarningLabelModel.status == status)
    if active is not None:
        base = base.where(WarningLabelModel.is_active == active)
        count_q = count_q.where(WarningLabelModel.is_active == active)
    if search:
        pattern = f"%{search}%"
        predicate = or_(
            WarningLabelModel.title.ilike(pattern),
            WarningLabelModel.text_en.ilike(pattern),
            WarningLabelModel.code.ilike(pattern),
        )
        base = base.where(predicate)
        count_q = count_q.where(predicate)

    total = (await db.execute(count_q)).scalar_one()
    rows = (
        await db.execute(
            base.order_by(WarningLabelModel.code).offset(offset).limit(limit)
        )
    ).scalars().all()

    return WarningLabelListResponse(
        warning_labels=[_model_to_response(w) for w in rows],
        total=total,
    )


@router.get("/{label_id}", response_model=WarningLabel)
async def get_warning_label(
    label_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WarningLabel:
    """Get a single warning label by id (tenant-scoped)."""
    label = await _get_label(db, _user.tenant_id, label_id)
    return _model_to_response(label)


@router.post("", response_model=WarningLabel, status_code=201)
async def create_warning_label(
    req: WarningLabelCreateRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WarningLabel:
    """Create a new warning label; starts in ``pending`` + inactive."""
    _ensure_capability(_user, Capability.WARNING_LABEL_EDIT)

    label = WarningLabelModel(
        tenant_id=_user.tenant_id,
        code=req.code,
        title=req.title,
        text_en=req.text,
        text_es=req.text_es,
        text_fr=req.text_fr,
        region=req.region,
        placement=req.placement,
        icon_asset_hash=req.icon_asset_hash,
        size_mm_width=req.size_mm_width,
        size_mm_height=req.size_mm_height,
        trigger_conditions=req.trigger_conditions,
        variants=req.variants,
        status=_STATUS_PENDING,
        is_active=False,
        created_by=_user.user_id,
    )
    db.add(label)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Warning label with code {req.code!r} already exists",
        )
    await db.refresh(label)
    return _model_to_response(label)


@router.put("/{label_id}", response_model=WarningLabel)
async def update_warning_label(
    label_id: str,
    req: WarningLabelUpdateRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WarningLabel:
    """Update a warning label.

    Once a label has been approved its ``code`` is treated as immutable:
    updates to other fields are still permitted (regulatory text can be
    revised under Legal's direction), but we never rename an approved
    label and never silently flip it back to ``pending``.
    """
    _ensure_capability(_user, Capability.WARNING_LABEL_EDIT)

    label = await _get_label(db, _user.tenant_id, label_id)

    if req.title is not None:
        label.title = req.title
    if req.text is not None:
        label.text_en = req.text
    if req.text_es is not None:
        label.text_es = req.text_es
    if req.text_fr is not None:
        label.text_fr = req.text_fr
    if req.region is not None:
        label.region = req.region
    if req.placement is not None:
        label.placement = req.placement
    if req.size_mm_width is not None:
        label.size_mm_width = req.size_mm_width
    if req.size_mm_height is not None:
        label.size_mm_height = req.size_mm_height
    if req.trigger_conditions is not None:
        label.trigger_conditions = req.trigger_conditions
    if req.variants is not None:
        label.variants = req.variants
    if req.icon_asset_hash is not None:
        label.icon_asset_hash = req.icon_asset_hash

    await db.commit()
    await db.refresh(label)
    return _model_to_response(label)


@router.post("/{label_id}/approve", response_model=WarningLabel)
async def approve_warning_label(
    label_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WarningLabel:
    """Mark a pending/rejected label as approved + active."""
    _ensure_capability(_user, Capability.WARNING_LABEL_EDIT)

    label = await _get_label(db, _user.tenant_id, label_id)
    if label.status == _STATUS_APPROVED:
        raise HTTPException(status_code=409, detail="Label is already approved")
    if label.status == _STATUS_DEPRECATED:
        raise HTTPException(
            status_code=409, detail="Deprecated label cannot be re-approved"
        )

    label.status = _STATUS_APPROVED
    label.is_active = True
    label.approved_by = _user.user_id
    label.approved_at = datetime.now(timezone.utc)
    label.rejected_reason = None
    await db.commit()
    await db.refresh(label)
    return _model_to_response(label)


@router.post("/{label_id}/reject", response_model=WarningLabel)
async def reject_warning_label(
    label_id: str,
    body: RejectRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WarningLabel:
    """Mark a pending label as rejected (requires a reason)."""
    _ensure_capability(_user, Capability.WARNING_LABEL_EDIT)

    label = await _get_label(db, _user.tenant_id, label_id)
    if label.status == _STATUS_APPROVED:
        raise HTTPException(
            status_code=409,
            detail="Cannot reject an approved label; deprecate it instead",
        )

    label.status = _STATUS_REJECTED
    label.is_active = False
    label.rejected_reason = body.reason
    label.approved_by = None
    label.approved_at = None
    await db.commit()
    await db.refresh(label)
    return _model_to_response(label)


@router.post("/{label_id}/deprecate", response_model=WarningLabel)
async def deprecate_warning_label(
    label_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WarningLabel:
    """Retire an approved label without deleting it."""
    _ensure_capability(_user, Capability.WARNING_LABEL_EDIT)

    label = await _get_label(db, _user.tenant_id, label_id)
    if label.status != _STATUS_APPROVED:
        raise HTTPException(
            status_code=409, detail="Only approved labels can be deprecated"
        )

    label.status = _STATUS_DEPRECATED
    label.is_active = False
    await db.commit()
    await db.refresh(label)
    return _model_to_response(label)
