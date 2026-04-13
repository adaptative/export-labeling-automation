"""Audit log endpoints with search, filtering, and pagination."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

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


# ── Stub data ───────────────────────────────────────────────────────────────

_ENTRIES: List[AuditEntry] = [
    AuditEntry(id="aud-001", timestamp="2026-04-12T14:32:00Z", actor="sarah.chen@nakoda.com",
               actor_type="user", action="APPROVE", resource_type="order", resource_id="PO-2065",
               detail="Approved compliance report for PO-2065", ip_address="10.0.1.42",
               metadata={"previous_status": "pending", "new_status": "approved"}),
    AuditEntry(id="aud-002", timestamp="2026-04-12T14:28:00Z", actor="composer-agent-v3",
               actor_type="agent", action="GENERATE", resource_type="artifact", resource_id="art-001",
               detail="Generated fused item SVG for PO-2065", ip_address="10.0.2.10"),
    AuditEntry(id="aud-003", timestamp="2026-04-12T14:15:00Z", actor="validator-agent-v2",
               actor_type="agent", action="VALIDATE", resource_type="compliance_report", resource_id="rpt-012",
               detail="Validated Prop 65 compliance for PO-2065", ip_address="10.0.2.11"),
    AuditEntry(id="aud-004", timestamp="2026-04-12T13:50:00Z", actor="system",
               actor_type="system", action="CREATE", resource_type="order", resource_id="PO-2070",
               detail="Order PO-2070 created from EDI import", ip_address="10.0.0.1"),
    AuditEntry(id="aud-005", timestamp="2026-04-12T13:45:00Z", actor="mike.johnson@nakoda.com",
               actor_type="user", action="UPDATE", resource_type="rule", resource_id="rule-003",
               detail="Updated furniture tip-over height threshold from 30 to 27 inches", ip_address="10.0.1.55",
               metadata={"field": "height_inches", "old_value": 30, "new_value": 27}),
    AuditEntry(id="aud-006", timestamp="2026-04-12T12:30:00Z", actor="classifier-agent-v1",
               actor_type="agent", action="CLASSIFY", resource_type="document", resource_id="doc-445",
               detail="Classified invoice as commercial_invoice with 98% confidence", ip_address="10.0.2.12"),
    AuditEntry(id="aud-007", timestamp="2026-04-12T11:20:00Z", actor="sarah.chen@nakoda.com",
               actor_type="user", action="REJECT", resource_type="artifact", resource_id="art-008",
               detail="Rejected die-cut: incorrect bleed margins", ip_address="10.0.1.42"),
    AuditEntry(id="aud-008", timestamp="2026-04-11T16:45:00Z", actor="extractor-agent-v2",
               actor_type="agent", action="EXTRACT", resource_type="document", resource_id="doc-440",
               detail="Extracted 24 line items from packing list", ip_address="10.0.2.13"),
    AuditEntry(id="aud-009", timestamp="2026-04-11T15:30:00Z", actor="system",
               actor_type="system", action="CREATE", resource_type="notification", resource_id="ntf-120",
               detail="Sent compliance alert to importer", ip_address="10.0.0.1"),
    AuditEntry(id="aud-010", timestamp="2026-04-11T14:00:00Z", actor="admin@nakoda.com",
               actor_type="user", action="UPDATE", resource_type="user", resource_id="usr-005",
               detail="Changed role from OPS to COMPLIANCE", ip_address="10.0.1.10",
               metadata={"old_role": "OPS", "new_role": "COMPLIANCE"}),
    AuditEntry(id="aud-011", timestamp="2026-04-11T12:15:00Z", actor="composer-agent-v3",
               actor_type="agent", action="GENERATE", resource_type="artifact", resource_id="art-010",
               detail="Generated approval PDF for PO-2068", ip_address="10.0.2.10"),
    AuditEntry(id="aud-012", timestamp="2026-04-11T10:00:00Z", actor="system",
               actor_type="system", action="DELETE", resource_type="artifact", resource_id="art-005",
               detail="Purged expired draft artifact", ip_address="10.0.0.1"),
    AuditEntry(id="aud-013", timestamp="2026-04-10T17:30:00Z", actor="mike.johnson@nakoda.com",
               actor_type="user", action="CREATE", resource_type="rule", resource_id="rule-005",
               detail="Created new EU packaging directive rule", ip_address="10.0.1.55"),
    AuditEntry(id="aud-014", timestamp="2026-04-10T16:00:00Z", actor="validator-agent-v2",
               actor_type="agent", action="VALIDATE", resource_type="order", resource_id="PO-2067",
               detail="Validation failed: missing CE mark for EU shipment", ip_address="10.0.2.11"),
    AuditEntry(id="aud-015", timestamp="2026-04-10T14:20:00Z", actor="sarah.chen@nakoda.com",
               actor_type="user", action="APPROVE", resource_type="order", resource_id="PO-2066",
               detail="Approved final labels for PO-2066", ip_address="10.0.1.42"),
    AuditEntry(id="aud-016", timestamp="2026-04-10T11:00:00Z", actor="system",
               actor_type="system", action="CREATE", resource_type="order", resource_id="PO-2067",
               detail="Order PO-2067 created from API import", ip_address="10.0.0.1"),
    AuditEntry(id="aud-017", timestamp="2026-04-09T15:45:00Z", actor="classifier-agent-v1",
               actor_type="agent", action="CLASSIFY", resource_type="document", resource_id="doc-438",
               detail="Classified document as packing_list with 95% confidence", ip_address="10.0.2.12"),
    AuditEntry(id="aud-018", timestamp="2026-04-09T13:10:00Z", actor="admin@nakoda.com",
               actor_type="user", action="UPDATE", resource_type="settings", resource_id="sso-config",
               detail="Enabled Google OIDC SSO provider", ip_address="10.0.1.10"),
    AuditEntry(id="aud-019", timestamp="2026-04-09T10:30:00Z", actor="composer-agent-v3",
               actor_type="agent", action="GENERATE", resource_type="artifact", resource_id="art-007",
               detail="Generated line drawing for item ITM-2066-003", ip_address="10.0.2.10"),
    AuditEntry(id="aud-020", timestamp="2026-04-08T16:00:00Z", actor="system",
               actor_type="system", action="CREATE", resource_type="order", resource_id="PO-2065",
               detail="Order PO-2065 created from EDI import", ip_address="10.0.0.1"),
]


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
) -> AuditListResponse:
    """List audit log entries with search, filter, and pagination."""
    results = list(_ENTRIES)

    if search:
        q = search.lower()
        results = [
            e for e in results
            if q in e.actor.lower() or q in e.resource_id.lower() or q in e.detail.lower()
        ]

    if actor_type:
        results = [e for e in results if e.actor_type == actor_type]

    if action:
        results = [e for e in results if e.action == action]

    # Sort
    reverse = sort_order == "desc"
    if sort_by == "timestamp":
        results.sort(key=lambda e: e.timestamp, reverse=reverse)
    elif sort_by == "actor":
        results.sort(key=lambda e: e.actor, reverse=reverse)
    elif sort_by == "action":
        results.sort(key=lambda e: e.action, reverse=reverse)

    total = len(results)
    return AuditListResponse(
        entries=results[offset:offset + limit],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{entry_id}", response_model=AuditEntry)
async def get_audit_entry(entry_id: str) -> AuditEntry:
    """Get a single audit log entry by ID."""
    for entry in _ENTRIES:
        if entry.id == entry_id:
            return entry
    raise HTTPException(status_code=404, detail="Audit entry not found")
