"""Compliance rule endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

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


# ── Mock data ────────────────────────────────────────────────────────────────

_MOCK_RULES: list[ComplianceRule] = [
    ComplianceRule(
        id="rule-001",
        code="PROP65",
        version=3,
        title="California Proposition 65 Warning",
        description="Products containing chemicals known to the State of California to cause cancer or reproductive harm must carry a Prop 65 warning label.",
        region="US-CA",
        placement="product",
        active=True,
        updated_at=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
    ),
    ComplianceRule(
        id="rule-002",
        code="CPSIA",
        version=2,
        title="CPSIA Lead & Phthalate Tracking",
        description="Children's products must include tracking labels per the Consumer Product Safety Improvement Act.",
        region="US",
        placement="both",
        active=True,
        updated_at=datetime(2026, 2, 15, 0, 0, 0, tzinfo=timezone.utc),
    ),
    ComplianceRule(
        id="rule-003",
        code="FCC15",
        version=1,
        title="FCC Part 15 Declaration",
        description="Electronic devices must carry the FCC Part 15 compliance statement on the carton.",
        region="US",
        placement="carton",
        active=True,
        updated_at=datetime(2026, 1, 20, 0, 0, 0, tzinfo=timezone.utc),
    ),
    ComplianceRule(
        id="rule-004",
        code="CHOKING_HAZARD",
        version=2,
        title="Small Parts Choking Hazard Warning",
        description="Toys and children's products with small parts must include ASTM F963 choking hazard warning.",
        region="US",
        placement="both",
        active=True,
        updated_at=datetime(2026, 3, 10, 0, 0, 0, tzinfo=timezone.utc),
    ),
    ComplianceRule(
        id="rule-005",
        code="COUNTRY_OF_ORIGIN",
        version=1,
        title="Country of Origin Marking",
        description="All imported goods must be marked with the country of origin per 19 CFR 134.",
        region="US",
        placement="carton",
        active=True,
        updated_at=datetime(2025, 12, 1, 0, 0, 0, tzinfo=timezone.utc),
    ),
]


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=RuleListResponse)
async def list_rules(
    region: Optional[str] = Query(None, description="Filter by region (e.g. US, US-CA, EU)"),
    placement: Optional[str] = Query(None, description="Filter by placement: carton, product, both, hangtag"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> RuleListResponse:
    """List compliance rules with optional filtering."""
    results = _MOCK_RULES
    if region:
        results = [r for r in results if r.region == region]
    if placement:
        results = [r for r in results if r.placement == placement]
    if active is not None:
        results = [r for r in results if r.active == active]
    total = len(results)
    return RuleListResponse(rules=results[offset : offset + limit], total=total)


@router.get("/{rule_id}", response_model=ComplianceRule)
async def get_rule(rule_id: str) -> ComplianceRule:
    """Get a single compliance rule by ID."""
    rule = next((r for r in _MOCK_RULES if r.id == rule_id), None)
    if rule is None:
        return _MOCK_RULES[0]
    return rule
