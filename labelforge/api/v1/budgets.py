"""Budget and cost-breaker endpoints."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.core.auth import TokenPayload
from labelforge.db.session import get_db
from labelforge.db.models import BudgetTier, BreakerEvent as BreakerEventModel, CostEvent

router = APIRouter(prefix="/budgets", tags=["budgets"])


# -- Models ------------------------------------------------------------------


class SpendingTier(BaseModel):
    id: str
    name: str
    current_spend: float
    cap: float
    unit: str
    trend_pct: float
    breaker_active: bool


class CurrentSpendResponse(BaseModel):
    tiers: List[SpendingTier]


class BreakerEvent(BaseModel):
    id: str
    timestamp: str
    tier: str
    event_type: str  # breach | recovery
    triggered_by: str
    action: str
    status: str  # active | resolved


class BreakerEventsResponse(BaseModel):
    events: List[BreakerEvent]
    total: int
    limit: int
    offset: int


class UpdateCapRequest(BaseModel):
    tier: str
    new_cap: float = Field(gt=0)
    reason: str = Field(min_length=1)


class UpdateCapResponse(BaseModel):
    tier: SpendingTier
    previous_cap: float
    reason: str
    updated_at: str


# -- Endpoints ---------------------------------------------------------------


@router.get("/current-spend", response_model=CurrentSpendResponse)
async def get_current_spend(
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentSpendResponse:
    """Return current spending across all budget tiers."""
    # Fetch all budget tiers for this tenant
    tiers_result = await db.execute(
        select(BudgetTier).where(BudgetTier.tenant_id == _user.tenant_id)
    )
    tiers = tiers_result.scalars().all()

    # Sum today's cost events per scope
    today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)
    spend_q = (
        select(
            CostEvent.scope,
            func.coalesce(func.sum(CostEvent.amount_usd), 0).label("total"),
        )
        .where(CostEvent.tenant_id == _user.tenant_id)
        .where(CostEvent.created_at >= today_start)
        .group_by(CostEvent.scope)
    )
    spend_result = await db.execute(spend_q)
    spend_map = {row.scope: float(row.total) for row in spend_result}

    spending_tiers = [
        SpendingTier(
            id=t.id,
            name=t.name,
            current_spend=spend_map.get(t.id, 0.0),
            cap=t.cap,
            unit=t.unit,
            trend_pct=0.0,
            breaker_active=t.breaker_active,
        )
        for t in tiers
    ]

    return CurrentSpendResponse(tiers=spending_tiers)


@router.get("/events", response_model=BreakerEventsResponse)
async def get_breaker_events(
    tier: Optional[str] = Query(None, description="Filter by tier ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BreakerEventsResponse:
    """Return breaker event history with optional tier filter."""
    q = (
        select(BreakerEventModel)
        .where(BreakerEventModel.tenant_id == _user.tenant_id)
    )
    if tier:
        q = q.where(BreakerEventModel.tier_id == tier)

    # Get total count
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch page
    q = q.order_by(BreakerEventModel.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    rows = result.scalars().all()

    events = [
        BreakerEvent(
            id=e.id,
            timestamp=e.created_at.isoformat() if e.created_at else "",
            tier=e.tier_id,
            event_type=e.event_type,
            triggered_by=e.triggered_by,
            action=e.action,
            status=e.status,
        )
        for e in rows
    ]

    return BreakerEventsResponse(
        events=events,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put("/tenant/{tenant_id}/caps", response_model=UpdateCapResponse)
async def update_budget_cap(
    tenant_id: str,
    body: UpdateCapRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UpdateCapResponse:
    """Update budget cap for a specific tier."""
    result = await db.execute(
        select(BudgetTier)
        .where(BudgetTier.tenant_id == tenant_id)
        .where(BudgetTier.id == body.tier)
    )
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=404, detail="Tier not found")

    previous_cap = tier.cap
    tier.cap = body.new_cap
    tier.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(tier)

    # Compute current spend for the response
    today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)
    spend_result = await db.execute(
        select(func.coalesce(func.sum(CostEvent.amount_usd), 0))
        .where(CostEvent.tenant_id == tenant_id)
        .where(CostEvent.scope == tier.id)
        .where(CostEvent.created_at >= today_start)
    )
    current_spend = float(spend_result.scalar() or 0)

    updated = SpendingTier(
        id=tier.id,
        name=tier.name,
        current_spend=current_spend,
        cap=tier.cap,
        unit=tier.unit,
        trend_pct=0.0,
        breaker_active=tier.breaker_active,
    )

    return UpdateCapResponse(
        tier=updated,
        previous_cap=previous_cap,
        reason=body.reason,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
