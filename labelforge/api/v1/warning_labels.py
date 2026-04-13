"""Warning label endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.core.auth import TokenPayload
from labelforge.db.models import WarningLabel as WarningLabelModel
from labelforge.db.session import get_db

router = APIRouter(prefix="/warning-labels", tags=["warning-labels"])


# ── Response models ──────────────────────────────────────────────────────────


class WarningLabel(BaseModel):
    id: str
    code: str
    title: str
    text: str
    region: str
    placement: str
    icon_asset_hash: Optional[str] = None
    active: bool = True
    updated_at: datetime


class WarningLabelListResponse(BaseModel):
    warning_labels: list[WarningLabel]
    total: int


# ── Helpers ──────────────────────────────────────────────────────────────────


def _model_to_response(w: WarningLabelModel) -> WarningLabel:
    return WarningLabel(
        id=w.id,
        code=w.code,
        title=w.title,
        text=w.text_en,
        region=w.region,
        placement=w.placement,
        icon_asset_hash=w.icon_asset_hash,
        active=w.is_active,
        updated_at=w.updated_at or w.created_at,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=WarningLabelListResponse)
async def list_warning_labels(
    region: Optional[str] = Query(None, description="Filter by region (e.g. US, US-CA, EU)"),
    placement: Optional[str] = Query(None, description="Filter by placement: carton, product, both, hangtag"),
    code: Optional[str] = Query(None, description="Filter by warning code"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WarningLabelListResponse:
    """List warning labels with optional filtering."""
    query = select(WarningLabelModel).where(WarningLabelModel.tenant_id == _user.tenant_id)
    count_query = select(func.count()).select_from(WarningLabelModel).where(WarningLabelModel.tenant_id == _user.tenant_id)

    if region:
        query = query.where(WarningLabelModel.region == region)
        count_query = count_query.where(WarningLabelModel.region == region)
    if placement:
        query = query.where(WarningLabelModel.placement == placement)
        count_query = count_query.where(WarningLabelModel.placement == placement)
    if code:
        query = query.where(WarningLabelModel.code == code)
        count_query = count_query.where(WarningLabelModel.code == code)
    if active is not None:
        query = query.where(WarningLabelModel.is_active == active)
        count_query = count_query.where(WarningLabelModel.is_active == active)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(WarningLabelModel.code).offset(offset).limit(limit)
    result = await db.execute(query)
    labels = result.scalars().all()

    return WarningLabelListResponse(
        warning_labels=[_model_to_response(w) for w in labels],
        total=total,
    )


@router.get("/{label_id}", response_model=WarningLabel)
async def get_warning_label(
    label_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WarningLabel:
    """Get a single warning label by ID."""
    result = await db.execute(
        select(WarningLabelModel).where(
            WarningLabelModel.id == label_id,
            WarningLabelModel.tenant_id == _user.tenant_id,
        )
    )
    label = result.scalar_one_or_none()
    if label is None:
        raise HTTPException(status_code=404, detail="Warning label not found")

    return _model_to_response(label)
