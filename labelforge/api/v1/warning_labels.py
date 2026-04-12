"""Warning label endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

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


# ── Mock data ────────────────────────────────────────────────────────────────

_MOCK_LABELS: list[WarningLabel] = [
    WarningLabel(
        id="wl-001",
        code="PROP65_CANCER",
        title="Proposition 65 Cancer Warning",
        text="WARNING: This product can expose you to chemicals including lead, which is known to the State of California to cause cancer. For more information go to www.P65Warnings.ca.gov.",
        region="US-CA",
        placement="product",
        icon_asset_hash="sha256:prop65icon01",
        active=True,
        updated_at=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
    ),
    WarningLabel(
        id="wl-002",
        code="PROP65_REPRO",
        title="Proposition 65 Reproductive Harm Warning",
        text="WARNING: This product can expose you to chemicals including DEHP, which is known to the State of California to cause birth defects or other reproductive harm. For more information go to www.P65Warnings.ca.gov.",
        region="US-CA",
        placement="product",
        icon_asset_hash="sha256:prop65icon02",
        active=True,
        updated_at=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
    ),
    WarningLabel(
        id="wl-003",
        code="CHOKING_SMALL_PARTS",
        title="Choking Hazard - Small Parts",
        text="WARNING: CHOKING HAZARD - Small parts. Not for children under 3 years.",
        region="US",
        placement="both",
        icon_asset_hash="sha256:chokingicon01",
        active=True,
        updated_at=datetime(2026, 2, 15, 0, 0, 0, tzinfo=timezone.utc),
    ),
    WarningLabel(
        id="wl-004",
        code="CHOKING_SMALL_BALL",
        title="Choking Hazard - Small Ball",
        text="WARNING: CHOKING HAZARD - This toy is a small ball. Not for children under 3 years.",
        region="US",
        placement="both",
        icon_asset_hash="sha256:chokingicon02",
        active=True,
        updated_at=datetime(2026, 2, 15, 0, 0, 0, tzinfo=timezone.utc),
    ),
    WarningLabel(
        id="wl-005",
        code="FCC_PART15",
        title="FCC Part 15 Compliance Statement",
        text="This device complies with Part 15 of the FCC Rules. Operation is subject to the following two conditions: (1) this device may not cause harmful interference, and (2) this device must accept any interference received, including interference that may cause undesired operation.",
        region="US",
        placement="carton",
        icon_asset_hash=None,
        active=True,
        updated_at=datetime(2026, 1, 20, 0, 0, 0, tzinfo=timezone.utc),
    ),
]


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=WarningLabelListResponse)
async def list_warning_labels(
    region: Optional[str] = Query(None, description="Filter by region (e.g. US, US-CA, EU)"),
    placement: Optional[str] = Query(None, description="Filter by placement: carton, product, both, hangtag"),
    code: Optional[str] = Query(None, description="Filter by warning code"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> WarningLabelListResponse:
    """List warning labels with optional filtering."""
    results = _MOCK_LABELS
    if region:
        results = [wl for wl in results if wl.region == region]
    if placement:
        results = [wl for wl in results if wl.placement == placement]
    if code:
        results = [wl for wl in results if wl.code == code]
    if active is not None:
        results = [wl for wl in results if wl.active == active]
    total = len(results)
    return WarningLabelListResponse(
        warning_labels=results[offset : offset + limit], total=total
    )
