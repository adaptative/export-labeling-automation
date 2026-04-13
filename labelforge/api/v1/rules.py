"""Compliance rule endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.core.auth import TokenPayload
from labelforge.db.models import ComplianceRule as ComplianceRuleModel
from labelforge.db.session import get_db

router = APIRouter(prefix="/rules", tags=["rules"])


# ── Response models ──────────────────────────────────────────────────────────


class ComplianceRule(BaseModel):
    id: str
    code: str
    version: int
    title: str
    description: str
    region: str
    placement: str
    active: bool = True
    updated_at: datetime


class RuleListResponse(BaseModel):
    rules: list[ComplianceRule]
    total: int


# ── Helpers ──────────────────────────────────────────────────────────────────


def _model_to_response(r: ComplianceRuleModel) -> ComplianceRule:
    return ComplianceRule(
        id=r.id,
        code=r.rule_code,
        version=r.version,
        title=r.title,
        description=r.description or "",
        region=r.region,
        placement=r.placement,
        active=r.is_active,
        updated_at=r.updated_at or r.created_at,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=RuleListResponse)
async def list_rules(
    region: Optional[str] = Query(None, description="Filter by region (e.g. US, US-CA, EU)"),
    placement: Optional[str] = Query(None, description="Filter by placement: carton, product, both, hangtag"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RuleListResponse:
    """List compliance rules with optional filtering."""
    query = select(ComplianceRuleModel).where(ComplianceRuleModel.tenant_id == _user.tenant_id)
    count_query = select(func.count()).select_from(ComplianceRuleModel).where(ComplianceRuleModel.tenant_id == _user.tenant_id)

    if region:
        query = query.where(ComplianceRuleModel.region == region)
        count_query = count_query.where(ComplianceRuleModel.region == region)
    if placement:
        query = query.where(ComplianceRuleModel.placement == placement)
        count_query = count_query.where(ComplianceRuleModel.placement == placement)
    if active is not None:
        query = query.where(ComplianceRuleModel.is_active == active)
        count_query = count_query.where(ComplianceRuleModel.is_active == active)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(ComplianceRuleModel.rule_code).offset(offset).limit(limit)
    result = await db.execute(query)
    rules = result.scalars().all()

    return RuleListResponse(
        rules=[_model_to_response(r) for r in rules],
        total=total,
    )


@router.get("/{rule_id}", response_model=ComplianceRule)
async def get_rule(
    rule_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ComplianceRule:
    """Get a single compliance rule by ID."""
    result = await db.execute(
        select(ComplianceRuleModel).where(
            ComplianceRuleModel.id == rule_id,
            ComplianceRuleModel.tenant_id == _user.tenant_id,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    return _model_to_response(rule)
