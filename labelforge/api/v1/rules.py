"""Compliance rule endpoints.

TASK-025 implements the full rule-management lifecycle:

    POST   /rules                     — create a new rule in staging (is_active=False)
    GET    /rules                     — list rules (filterable by region/placement/active)
    GET    /rules/{rule_id}           — single rule
    PUT    /rules/{rule_id}           — update a staged rule (not yet promoted)
    POST   /rules/dry-run             — evaluate a proposed rule against scoped items
    POST   /rules/{rule_id}/promote   — activate a staged rule (RULE_PROMOTE cap.)
    POST   /rules/{rule_id}/rollback  — deactivate an active rule and reactivate
                                         the previous version (RULE_PROMOTE cap.)
    GET    /rules/audit-log           — audit trail for rule mutations

Staging model: a newly created rule starts ``is_active=False``.  Promoting it
sets ``is_active=True`` on that version and flips every older active version
of the same ``rule_code`` to ``is_active=False``.  Rollback reverses the most
recent promote by deactivating the given version and reactivating the latest
older version of the same code.

Each mutating endpoint writes an ``AuditLog`` row with
``resource_type="compliance_rule"`` so ``GET /rules/audit-log`` can render
the full history.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.compliance.dry_run import DryRunEngine
from labelforge.compliance.rule_engine import RuleContext, RuleDefinition
from labelforge.core.auth import Capability, Role, TokenPayload
from labelforge.db.models import AuditLog, ComplianceRule as ComplianceRuleModel, OrderItemModel
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
    logic: Optional[dict] = None
    updated_at: datetime


class RuleListResponse(BaseModel):
    rules: list[ComplianceRule]
    total: int


class RuleCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=500)
    description: str = ""
    region: str = "US"
    placement: str = "both"
    logic: Optional[dict] = None


class RuleUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    region: Optional[str] = None
    placement: Optional[str] = None
    logic: Optional[dict] = None


class DryRunRequest(BaseModel):
    proposed: RuleCreateRequest
    order_id: Optional[str] = None
    item_ids: Optional[list[str]] = None
    sample_contexts: Optional[list[dict]] = None


class DryRunResponseModel(BaseModel):
    items_evaluated: int
    newly_failing: list[str]
    newly_passing: list[str]
    unchanged: list[str]


class RuleMutationResponse(BaseModel):
    rule_id: str
    code: str
    version: int
    active: bool
    message: str


class AuditEntryModel(BaseModel):
    id: str
    action: str
    actor: Optional[str] = None
    actor_type: str
    rule_id: Optional[str] = None
    detail: Optional[str] = None
    created_at: datetime


class AuditLogResponse(BaseModel):
    entries: list[AuditEntryModel]
    total: int


# ── Helpers ──────────────────────────────────────────────────────────────────


def _ensure_capability(user: TokenPayload, cap: Capability) -> None:
    """Raise ``HTTPException(403)`` when the token lacks the given capability."""
    from labelforge.core.auth import ROLE_CAPABILITIES

    role_caps = ROLE_CAPABILITIES.get(user.role, set())
    if cap in role_caps or cap in user.capabilities:
        return
    raise HTTPException(status_code=403, detail=f"Missing capability: {cap.value}")


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
        logic=r.logic,
        updated_at=r.updated_at or r.created_at,
    )


def _row_to_definition(r: ComplianceRuleModel) -> RuleDefinition:
    """Project a DB row to the in-memory DSL ``RuleDefinition`` used by the
    rule engine.

    The ``logic`` column is expected to hold
    ``{"conditions": <AST>, "requirements": <AST>, "category"?: str}``.  When
    either AST is missing we substitute ``{"op": "true"}`` so the compiler
    short-circuits to "Not applicable" rather than crashing.
    """
    logic = r.logic or {}
    conditions = logic.get("conditions") or {"op": "true"}
    requirements = logic.get("requirements") or {"op": "true"}
    category = logic.get("category") or "compliance"
    return RuleDefinition(
        code=r.rule_code,
        version=r.version,
        title=r.title,
        country=r.region,
        category=category,
        placement=r.placement,
        conditions=conditions,
        requirements=requirements,
    )


def _dict_to_context(item_no: str, data: dict | None) -> RuleContext:
    """Best-effort conversion of an ``OrderItem.data`` payload into a
    ``RuleContext`` consumed by the dry-run engine."""
    data = data or {}
    known = {"material", "destination", "weight", "product_type", "dimensions"}
    custom = {k: v for k, v in data.items() if k not in known}
    return RuleContext(
        item_no=item_no,
        material=data.get("material"),
        destination=data.get("destination", "US"),
        weight=float(data.get("weight", 0.0) or 0.0),
        product_type=data.get("product_type"),
        dimensions=data.get("dimensions"),
        custom=custom,
    )


def _request_to_definition(req: RuleCreateRequest, version: int = 1) -> RuleDefinition:
    logic = req.logic or {}
    return RuleDefinition(
        code=req.code,
        version=version,
        title=req.title,
        country=req.region,
        category=logic.get("category") or "compliance",
        placement=req.placement,
        conditions=logic.get("conditions") or {"op": "true"},
        requirements=logic.get("requirements") or {"op": "true"},
    )


async def _write_audit(
    db: AsyncSession,
    *,
    user: TokenPayload,
    action: str,
    rule: ComplianceRuleModel,
    detail: str,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """Append an ``AuditLog`` row for a rule mutation.

    Commit is performed by the caller so the rule row and the audit row
    land in the same transaction.
    """
    entry = AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        actor=user.user_id,
        actor_type="user",
        action=action,
        resource_type="compliance_rule",
        resource_id=rule.id,
        detail=detail,
        details={
            "rule_code": rule.rule_code,
            "version": rule.version,
            **(extra or {}),
        },
    )
    db.add(entry)


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=RuleListResponse)
async def list_rules(
    region: Optional[str] = Query(None, description="Filter by region (e.g. US, US-CA, EU)"),
    placement: Optional[str] = Query(None, description="Filter by placement: carton, product, both, hangtag"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    code: Optional[str] = Query(None, description="Filter by rule_code (exact match)"),
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
    if code:
        query = query.where(ComplianceRuleModel.rule_code == code)
        count_query = count_query.where(ComplianceRuleModel.rule_code == code)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(ComplianceRuleModel.rule_code, desc(ComplianceRuleModel.version)).offset(offset).limit(limit)
    result = await db.execute(query)
    rules = result.scalars().all()

    return RuleListResponse(
        rules=[_model_to_response(r) for r in rules],
        total=total,
    )


@router.get("/audit-log", response_model=AuditLogResponse)
async def rule_audit_log(
    rule_id: Optional[str] = Query(None, description="Filter to a single rule"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuditLogResponse:
    """Audit trail for compliance-rule mutations (``create``, ``update``,
    ``promote``, ``rollback``).
    """
    _ensure_capability(_user, Capability.AUDIT_VIEW)

    base = select(AuditLog).where(
        AuditLog.tenant_id == _user.tenant_id,
        AuditLog.resource_type == "compliance_rule",
    )
    count_q = select(func.count()).select_from(AuditLog).where(
        AuditLog.tenant_id == _user.tenant_id,
        AuditLog.resource_type == "compliance_rule",
    )
    if rule_id:
        base = base.where(AuditLog.resource_id == rule_id)
        count_q = count_q.where(AuditLog.resource_id == rule_id)

    total = (await db.execute(count_q)).scalar_one()
    rows = (
        await db.execute(
            base.order_by(desc(AuditLog.created_at)).offset(offset).limit(limit)
        )
    ).scalars().all()

    return AuditLogResponse(
        entries=[
            AuditEntryModel(
                id=row.id,
                action=row.action,
                actor=row.actor,
                actor_type=row.actor_type,
                rule_id=row.resource_id,
                detail=row.detail,
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
    )


@router.post("", response_model=ComplianceRule, status_code=201)
async def create_rule(
    req: RuleCreateRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ComplianceRule:
    """Create a new rule in staging. Requires ``rule.propose``.

    If a rule with ``rule_code`` already exists, the new row takes
    ``version = max(existing) + 1`` so every previous version is preserved.
    The new rule is always created with ``is_active=False`` — it becomes
    live only after a successful ``/promote`` call.
    """
    _ensure_capability(_user, Capability.RULE_PROPOSE)

    existing_versions = (
        await db.execute(
            select(func.max(ComplianceRuleModel.version)).where(
                ComplianceRuleModel.tenant_id == _user.tenant_id,
                ComplianceRuleModel.rule_code == req.code,
            )
        )
    ).scalar()
    next_version = (existing_versions or 0) + 1

    rule = ComplianceRuleModel(
        tenant_id=_user.tenant_id,
        rule_code=req.code,
        version=next_version,
        title=req.title,
        description=req.description,
        region=req.region,
        placement=req.placement,
        logic=req.logic,
        is_active=False,
    )
    db.add(rule)
    await db.flush()
    await _write_audit(
        db,
        user=_user,
        action="create",
        rule=rule,
        detail=f"Created rule {req.code} v{next_version} in staging",
    )
    await db.commit()
    await db.refresh(rule)
    return _model_to_response(rule)


@router.post("/dry-run", response_model=DryRunResponseModel)
async def dry_run_rule(
    req: DryRunRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DryRunResponseModel:
    """Evaluate a proposed rule against scoped items and report drift.

    Scope is resolved in priority order:
      1. ``sample_contexts`` — inline contexts (caller-provided).
      2. ``item_ids`` — explicit order-item IDs in the caller's tenant.
      3. ``order_id`` — all items in the given order.

    The engine compares compliance outcomes before and after applying the
    proposed rule and returns the count of items in each bucket.
    """
    _ensure_capability(_user, Capability.RULE_PROPOSE)

    # Load current active rule set for the tenant.
    existing_rows = (
        await db.execute(
            select(ComplianceRuleModel).where(
                ComplianceRuleModel.tenant_id == _user.tenant_id,
                ComplianceRuleModel.is_active == True,  # noqa: E712
            )
        )
    ).scalars().all()
    existing_defs = [_row_to_definition(r) for r in existing_rows]

    # Resolve scope → list[RuleContext].
    contexts: list[RuleContext] = []
    if req.sample_contexts:
        for i, d in enumerate(req.sample_contexts):
            contexts.append(_dict_to_context(d.get("item_no") or f"sample-{i}", d))
    else:
        q = select(OrderItemModel).where(OrderItemModel.tenant_id == _user.tenant_id)
        if req.item_ids:
            q = q.where(OrderItemModel.id.in_(req.item_ids))
        elif req.order_id:
            q = q.where(OrderItemModel.order_id == req.order_id)
        else:
            q = q.limit(100)
        items = (await db.execute(q)).scalars().all()
        contexts = [_dict_to_context(it.item_no, it.data) for it in items]

    proposed = _request_to_definition(req.proposed)
    report = DryRunEngine().run(proposed, existing_defs, contexts)
    return DryRunResponseModel(
        items_evaluated=report.items_evaluated,
        newly_failing=report.newly_failing,
        newly_passing=report.newly_passing,
        unchanged=report.unchanged,
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


@router.put("/{rule_id}", response_model=ComplianceRule)
async def update_rule(
    rule_id: str,
    req: RuleUpdateRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ComplianceRule:
    """Update a staged rule.

    Rules that have been promoted (``is_active=True``) are immutable — edits
    must go through a new version created via ``POST /rules`` followed by
    promote.  Returns 409 when attempting to edit an active rule.
    """
    _ensure_capability(_user, Capability.RULE_PROPOSE)

    rule = (
        await db.execute(
            select(ComplianceRuleModel).where(
                ComplianceRuleModel.id == rule_id,
                ComplianceRuleModel.tenant_id == _user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    if rule.is_active:
        raise HTTPException(
            status_code=409,
            detail="Cannot edit a promoted rule — create a new version instead",
        )

    changed: dict[str, Any] = {}
    if req.title is not None:
        rule.title = req.title
        changed["title"] = req.title
    if req.description is not None:
        rule.description = req.description
        changed["description"] = req.description
    if req.region is not None:
        rule.region = req.region
        changed["region"] = req.region
    if req.placement is not None:
        rule.placement = req.placement
        changed["placement"] = req.placement
    if req.logic is not None:
        rule.logic = req.logic
        changed["logic"] = True

    if changed:
        await _write_audit(
            db,
            user=_user,
            action="update",
            rule=rule,
            detail=f"Updated staged rule {rule.rule_code} v{rule.version}",
            extra={"fields": list(changed.keys())},
        )
    await db.commit()
    await db.refresh(rule)
    return _model_to_response(rule)


@router.post("/{rule_id}/promote", response_model=RuleMutationResponse)
async def promote_rule(
    rule_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RuleMutationResponse:
    """Promote a staged rule to active.

    Sets ``is_active=True`` on the target version and flips every other
    version of the same ``rule_code`` in the tenant to ``is_active=False``.
    Requires ``rule.promote`` capability (ADMIN or COMPLIANCE).
    """
    _ensure_capability(_user, Capability.RULE_PROMOTE)

    target = (
        await db.execute(
            select(ComplianceRuleModel).where(
                ComplianceRuleModel.id == rule_id,
                ComplianceRuleModel.tenant_id == _user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    if target.is_active:
        raise HTTPException(status_code=409, detail="Rule is already active")

    # Deactivate other versions of the same code.
    siblings = (
        await db.execute(
            select(ComplianceRuleModel).where(
                ComplianceRuleModel.tenant_id == _user.tenant_id,
                ComplianceRuleModel.rule_code == target.rule_code,
                ComplianceRuleModel.id != target.id,
                ComplianceRuleModel.is_active == True,  # noqa: E712
            )
        )
    ).scalars().all()
    deactivated_ids = [s.id for s in siblings]
    for s in siblings:
        s.is_active = False
    target.is_active = True

    await _write_audit(
        db,
        user=_user,
        action="promote",
        rule=target,
        detail=f"Promoted {target.rule_code} v{target.version}",
        extra={"deactivated_rule_ids": deactivated_ids},
    )
    await db.commit()
    await db.refresh(target)

    return RuleMutationResponse(
        rule_id=target.id,
        code=target.rule_code,
        version=target.version,
        active=True,
        message=f"Promoted {target.rule_code} v{target.version}",
    )


@router.post("/{rule_id}/rollback", response_model=RuleMutationResponse)
async def rollback_rule(
    rule_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RuleMutationResponse:
    """Reverse the most recent promote.

    Deactivates the given rule (must be active) and reactivates the highest-
    numbered older version of the same ``rule_code``.  If no prior version
    exists, the rule simply becomes inactive.
    """
    _ensure_capability(_user, Capability.RULE_PROMOTE)

    target = (
        await db.execute(
            select(ComplianceRuleModel).where(
                ComplianceRuleModel.id == rule_id,
                ComplianceRuleModel.tenant_id == _user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    if not target.is_active:
        raise HTTPException(status_code=409, detail="Rule is not currently active")

    target.is_active = False

    previous = (
        await db.execute(
            select(ComplianceRuleModel)
            .where(
                ComplianceRuleModel.tenant_id == _user.tenant_id,
                ComplianceRuleModel.rule_code == target.rule_code,
                ComplianceRuleModel.id != target.id,
                ComplianceRuleModel.version < target.version,
            )
            .order_by(desc(ComplianceRuleModel.version))
            .limit(1)
        )
    ).scalar_one_or_none()

    restored_id: Optional[str] = None
    if previous is not None:
        previous.is_active = True
        restored_id = previous.id

    await _write_audit(
        db,
        user=_user,
        action="rollback",
        rule=target,
        detail=f"Rolled back {target.rule_code} v{target.version}"
        + (f" → v{previous.version}" if previous else " (no previous version)"),
        extra={"restored_rule_id": restored_id},
    )
    await db.commit()
    await db.refresh(target)

    return RuleMutationResponse(
        rule_id=target.id,
        code=target.rule_code,
        version=target.version,
        active=False,
        message=(
            f"Rolled back {target.rule_code} v{target.version}"
            + (f"; restored v{previous.version}" if previous else "")
        ),
    )
