"""Dashboard stats endpoint for KPI cards and activity feed."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from labelforge.api.v1.auth import get_current_user
from labelforge.core.auth import TokenPayload

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ── Response models ──────────────────────────────────────────────────────────


class KPICard(BaseModel):
    key: str
    label: str
    value: float
    detail: str
    trend: Optional[float] = None


class ActiveOrder(BaseModel):
    id: str
    po_number: str
    importer_id: str
    state: str
    item_count: int
    progress: int
    issues: int


class ActivityEntry(BaseModel):
    id: str
    timestamp: str
    actor: str
    actor_type: str
    detail: str


class AutomationPoint(BaseModel):
    date: str
    rate: float


class DashboardResponse(BaseModel):
    kpis: List[KPICard]
    active_orders: List[ActiveOrder]
    recent_activity: List[ActivityEntry]
    automation_series: List[AutomationPoint]


# ── Stub data ───────────────────────────────────────────────────────────────

_ACTIVE_ORDERS: List[ActiveOrder] = [
    ActiveOrder(id="ORD-2026-0042", po_number="PO-88210", importer_id="IMP-ACME",
                state="IN_PROGRESS", item_count=2, progress=65, issues=0),
    ActiveOrder(id="ORD-2026-0044", po_number="PO-88215", importer_id="IMP-ACME",
                state="HUMAN_BLOCKED", item_count=3, progress=35, issues=1),
    ActiveOrder(id="ORD-2026-0045", po_number="PO-90001", importer_id="IMP-GLOBEX",
                state="IN_PROGRESS", item_count=5, progress=80, issues=0),
]

_RECENT_ACTIVITY: List[ActivityEntry] = [
    ActivityEntry(id="act-001", timestamp="2026-04-13T08:12:00Z", actor="Composer Agent",
                  actor_type="agent", detail="Rendered die-cut for item A1001"),
    ActivityEntry(id="act-002", timestamp="2026-04-13T08:10:00Z", actor="Validator Agent",
                  actor_type="agent", detail="Validated compliance for PO-88210"),
    ActivityEntry(id="act-003", timestamp="2026-04-13T07:58:00Z", actor="Fusion Agent",
                  actor_type="agent", detail="Raised HiTL issue for item C3001"),
    ActivityEntry(id="act-004", timestamp="2026-04-13T07:40:00Z", actor="sarah.chen@nakoda.com",
                  actor_type="user", detail="Approved compliance report for PO-88210"),
    ActivityEntry(id="act-005", timestamp="2026-04-12T16:30:00Z", actor="Intake Agent",
                  actor_type="agent", detail="Classified 3 documents for PO-90001"),
    ActivityEntry(id="act-006", timestamp="2026-04-12T15:00:00Z", actor="admin@nakoda.com",
                  actor_type="user", detail="Updated Sagebrook protocol to v5"),
]

_AUTOMATION_SERIES: List[AutomationPoint] = [
    AutomationPoint(date=f"2026-03-{d:02d}", rate=round(60 + (d * 0.8) + (d % 3) * 2, 1))
    for d in range(15, 32)
] + [
    AutomationPoint(date=f"2026-04-{d:02d}", rate=round(72 + (d * 0.5) + (d % 4) * 1.5, 1))
    for d in range(1, 14)
]


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/stats", response_model=DashboardResponse)
async def get_dashboard_stats(
    _user: TokenPayload = Depends(get_current_user),
) -> DashboardResponse:
    """Return dashboard KPIs, active orders, activity feed, and automation trend."""
    kpis = [
        KPICard(key="active_orders", label="Active Orders", value=3,
                detail="5 total · 2 delivered", trend=12.0),
        KPICard(key="hitl_open", label="HiTL Open", value=2,
                detail="1 active · 1 waiting", trend=-5.0),
        KPICard(key="automation_rate", label="Automation Rate", value=78.5,
                detail="7-day rolling average", trend=3.2),
        KPICard(key="today_spend", label="Today Spend", value=184.22,
                detail="18% of daily budget", trend=8.5),
    ]

    return DashboardResponse(
        kpis=kpis,
        active_orders=_ACTIVE_ORDERS,
        recent_activity=_RECENT_ACTIVITY,
        automation_series=_AUTOMATION_SERIES,
    )
