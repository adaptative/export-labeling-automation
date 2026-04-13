"""Audit log endpoints with search, filtering, and pagination."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.core.auth import TokenPayload
from labelforge.db.models import AuditLog as AuditLogModel
from labelforge.db.session import get_db

router = APIRouter(prefix="/audit-log", tags=["audit-log"])


# ── Models ──────────────────────────────────────────────────────────────────


class AuditEntry(BaseModel):
    id: str
    timestamp: str
    actor: str
    actor_type: str  # user | agent | system
    action: str
    resource_type: str
    resource_id: str
    detail: str
    ip_address: str
    metadata: Optional[Dict[str, Any]] = None


class AuditListResponse(BaseModel):
    entries: List[AuditEntry]
    total: int
    limit: int
    offset: int


# ── Helpers ─────────────────────────────────────────────────────────────────

_SORT_COLUMNS = {
    "timestamp": AuditLogModel.created_at,
    "actor": AuditLogModel.actor,
    "action": AuditLogModel.action,
}


def _to_entry(e: AuditLogModel) -> AuditEntry:
    return AuditEntry(
        id=e.id,
        timestamp=e.created_at.isoformat(),
        actor=e.actor or "system",
        actor_type=e.actor_type,
        action=e.action,
        resource_type=e.resource_type,
        resource_id=e.resource_id or "",
        detail=e.detail or "",
        ip_address=e.ip_address or "",
        metadata=e.details,
    )


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("", response_model=AuditListResponse)
async def list_audit_entries(
    search: Optional[str] = Query(None, description="Search actor, resource_id, detail"),
    actor_type: Optional[str] = Query(None, description="Filter: user, agent, system"),
    action: Optional[str] = Query(None, description="Filter: CREATE, UPDATE, DELETE, APPROVE, etc."),
    sort_by: str = Query("timestamp", description="Sort field"),
    sort_order: str = Query("desc", description="asc or desc"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuditListResponse:
    """List audit log entries with search, filter, and pagination."""
    query = select(AuditLogModel)
    count_query = select(func.count()).select_from(AuditLogModel)

    if search:
        pattern = f"%{search}%"
        search_filter = or_(
            AuditLogModel.actor.ilike(pattern),
            AuditLogModel.resource_id.ilike(pattern),
            AuditLogModel.detail.ilike(pattern),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    if actor_type:
        query = query.where(AuditLogModel.actor_type == actor_type)
        count_query = count_query.where(AuditLogModel.actor_type == actor_type)

    if action:
        query = query.where(AuditLogModel.action == action)
        count_query = count_query.where(AuditLogModel.action == action)

    # Count
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Sort
    sort_col = _SORT_COLUMNS.get(sort_by, AuditLogModel.created_at)
    order_func = desc if sort_order == "desc" else asc
    query = query.order_by(order_func(sort_col))

    # Paginate
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    entries = result.scalars().all()

    return AuditListResponse(
        entries=[_to_entry(e) for e in entries],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{entry_id}", response_model=AuditEntry)
async def get_audit_entry(
    entry_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuditEntry:
    """Get a single audit log entry by ID."""
    result = await db.execute(
        select(AuditLogModel).where(AuditLogModel.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Audit entry not found")
    return _to_entry(entry)
