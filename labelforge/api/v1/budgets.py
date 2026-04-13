"""Budget and cost-breaker endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from labelforge.api.v1.auth import get_current_user
from labelforge.core.auth import TokenPayload

router = APIRouter(prefix="/budgets", tags=["budgets"])


# ── Models ──────────────────────────────────────────────────────────────────


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


# ── Stub data ───────────────────────────────────────────────────────────────

VALID_TIERS = {"llm_inference", "api_calls", "storage", "hitl"}

_TIERS: List[SpendingTier] = [
    SpendingTier(
        id="llm_inference", name="LLM Inference",
        current_spend=184.22, cap=1000.0, unit="$/day",
        trend_pct=12.5, breaker_active=False,
    ),
    SpendingTier(
        id="api_calls", name="API Calls",
        current_spend=3420, cap=10000, unit="calls/hour",
        trend_pct=-5.2, breaker_active=False,
    ),
    SpendingTier(
        id="storage", name="Storage",
        current_spend=42.8, cap=100.0, unit="GB",
        trend_pct=3.1, breaker_active=False,
    ),
    SpendingTier(
        id="hitl", name="Human Review (HiTL)",
        current_spend=18.5, cap=80.0, unit="hours/month",
        trend_pct=-8.0, breaker_active=False,
    ),
]

_EVENTS: List[BreakerEvent] = [
    BreakerEvent(id="evt-001", timestamp="2026-04-12T14:05:00Z", tier="llm_inference",
                 event_type="breach", triggered_by="cost_breaker_01",
                 action="Paused new inferences", status="resolved"),
    BreakerEvent(id="evt-002", timestamp="2026-04-12T14:35:00Z", tier="llm_inference",
                 event_type="recovery", triggered_by="cost_breaker_01",
                 action="Resumed inferences", status="resolved"),
    BreakerEvent(id="evt-003", timestamp="2026-04-11T09:12:00Z", tier="api_calls",
                 event_type="breach", triggered_by="rate_limiter_02",
                 action="Throttled API requests", status="resolved"),
    BreakerEvent(id="evt-004", timestamp="2026-04-11T09:42:00Z", tier="api_calls",
                 event_type="recovery", triggered_by="rate_limiter_02",
                 action="Restored normal rate", status="resolved"),
    BreakerEvent(id="evt-005", timestamp="2026-04-10T16:00:00Z", tier="storage",
                 event_type="breach", triggered_by="storage_monitor",
                 action="Blocked new uploads", status="resolved"),
    BreakerEvent(id="evt-006", timestamp="2026-04-10T17:30:00Z", tier="storage",
                 event_type="recovery", triggered_by="storage_monitor",
                 action="Uploads re-enabled", status="resolved"),
    BreakerEvent(id="evt-007", timestamp="2026-04-09T11:20:00Z", tier="hitl",
                 event_type="breach", triggered_by="hitl_cap_checker",
                 action="Queued new reviews", status="active"),
    BreakerEvent(id="evt-008", timestamp="2026-04-08T08:45:00Z", tier="llm_inference",
                 event_type="breach", triggered_by="cost_breaker_01",
                 action="Paused new inferences", status="resolved"),
]


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/current-spend", response_model=CurrentSpendResponse)
async def get_current_spend(_user: TokenPayload = Depends(get_current_user)) -> CurrentSpendResponse:
    """Return current spending across all 4 tiers."""
    return CurrentSpendResponse(tiers=_TIERS)


@router.get("/events", response_model=BreakerEventsResponse)
async def get_breaker_events(
    tier: Optional[str] = Query(None, description="Filter by tier ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
) -> BreakerEventsResponse:
    """Return breaker event history with optional tier filter."""
    results = _EVENTS
    if tier:
        results = [e for e in results if e.tier == tier]
    total = len(results)
    return BreakerEventsResponse(
        events=results[offset:offset + limit],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put("/tenant/{tenant_id}/caps", response_model=UpdateCapResponse)
async def update_budget_cap(
    tenant_id: str,
    body: UpdateCapRequest,
    _user: TokenPayload = Depends(get_current_user),
) -> UpdateCapResponse:
    """Update budget cap for a specific tier."""
    if body.tier not in VALID_TIERS:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {body.tier}")

    matching = [t for t in _TIERS if t.id == body.tier]
    if not matching:
        raise HTTPException(status_code=404, detail="Tier not found")

    tier = matching[0]
    previous_cap = tier.cap
    # In real impl, this would persist; stub just returns the updated view
    updated = tier.model_copy(update={"cap": body.new_cap})

    return UpdateCapResponse(
        tier=updated,
        previous_cap=previous_cap,
        reason=body.reason,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
