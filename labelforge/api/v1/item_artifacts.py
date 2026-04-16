"""Per-item artifact endpoints (INT-006, Sprint-13).

Backs the item-preview pages in the operator UI.  The composer, approval
PDF, and bundle generators produce blobs keyed on the Artifact table —
this router is the thin read-through layer that lets the frontend
stream the latest die-cut SVG, approval PDF, line drawing, or printer
bundle for a given order item, plus its state-transition history.

Every endpoint is tenant-scoped via :func:`get_current_user` and returns
404 on cross-tenant access so an importer user can never snoop another
tenant's item.

Endpoints
---------

* ``GET  /items/{item_id}/diecut-svg``      → ``image/svg+xml``
* ``GET  /items/{item_id}/approval-pdf``    → ``application/pdf``
* ``GET  /items/{item_id}/line-drawing``    → latest HiTL drawing SVG/PDF
* ``GET  /items/{item_id}/history``         → JSON state-transition log
* ``GET  /items/{item_id}/bundle``          → ``application/zip``

Storage
-------

Artifacts are streamed from :func:`labelforge.api.v1.documents.get_blob_store`
when the blob is present.  If the blob is missing (e.g. the artifact row
was seeded without a corresponding blob, which is the default in dev),
the endpoint falls back to a 404 with a structured ``reason`` payload so
the UI can show a "not yet generated" state rather than crashing.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.api.v1.documents import get_blob_store
from labelforge.core.auth import TokenPayload
from labelforge.db.models import Artifact, AuditLog, OrderItemModel
from labelforge.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/items", tags=["item-artifacts"])


# ── Response models ─────────────────────────────────────────────────────────


class ItemHistoryEntry(BaseModel):
    step: int = Field(..., description="Ordinal position in the log")
    at: str = Field(..., description="ISO 8601 timestamp")
    actor: Optional[str] = Field(None, description="Human or agent id")
    actor_type: str = Field("system", description="system | agent | human")
    action: str = Field(..., description="Logical event, e.g. 'state_changed'")
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    detail: Optional[str] = None


class ItemHistoryResponse(BaseModel):
    item_id: str
    item_no: str
    current_state: str
    events: list[ItemHistoryEntry]


# ── Internal helpers ────────────────────────────────────────────────────────


async def _load_item(
    db: AsyncSession, item_id: str, tenant_id: str
) -> OrderItemModel:
    """Fetch an item scoped to the caller's tenant — else 404."""
    result = await db.execute(
        select(OrderItemModel).where(
            OrderItemModel.id == item_id,
            OrderItemModel.tenant_id == tenant_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return item


async def _latest_artifact(
    db: AsyncSession, item_id: str, tenant_id: str, artifact_type: str,
) -> Optional[Artifact]:
    """Return the newest artifact of a given type for an item, or None."""
    result = await db.execute(
        select(Artifact)
        .where(
            Artifact.order_item_id == item_id,
            Artifact.tenant_id == tenant_id,
            Artifact.artifact_type == artifact_type,
        )
        .order_by(Artifact.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _stream_artifact(
    db: AsyncSession, item_id: str, tenant_id: str,
    artifact_type: str, default_mime: str,
) -> Response:
    """Load the latest artifact blob for a given item/type and return it."""
    await _load_item(db, item_id, tenant_id)  # tenant check first
    artifact = await _latest_artifact(db, item_id, tenant_id, artifact_type)
    if artifact is None:
        return JSONResponse(
            status_code=404,
            content={
                "reason": "not_generated",
                "detail": f"No {artifact_type} artifact available for this item yet.",
                "item_id": item_id,
            },
        )

    mime = artifact.mime_type or default_mime
    filename = (artifact.s3_key or "").split("/")[-1] or f"{artifact_type}"
    store = get_blob_store()
    try:
        data = await store.download(artifact.s3_key)
    except (FileNotFoundError, KeyError):
        # Seed data often references an s3_key without a real blob.
        return JSONResponse(
            status_code=404,
            content={
                "reason": "blob_missing",
                "detail": "Artifact row exists but the underlying blob is missing.",
                "artifact_id": artifact.id,
                "storage_key": artifact.s3_key,
            },
        )

    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Artifact-Id": artifact.id,
            "X-Content-Hash": artifact.content_hash or "",
        },
    )


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/{item_id}/diecut-svg")
async def get_item_diecut_svg(
    item_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return the latest die-cut SVG for an item."""
    return await _stream_artifact(
        db, item_id, _user.tenant_id,
        artifact_type="die_cut_svg",
        default_mime="image/svg+xml",
    )


@router.get("/{item_id}/approval-pdf")
async def get_item_approval_pdf(
    item_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return the latest approval PDF for an item.

    Note: approval PDFs are typically **order-scoped** but we persist a copy
    per-item so the preview page can stream without doing an order lookup
    first.  The composer workflow is responsible for attaching the same
    artifact row to every item in the order.
    """
    return await _stream_artifact(
        db, item_id, _user.tenant_id,
        artifact_type="approval_pdf",
        default_mime="application/pdf",
    )


@router.get("/{item_id}/line-drawing")
async def get_item_line_drawing(
    item_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return the latest HiTL line-drawing SVG (falls back to PDF)."""
    await _load_item(db, item_id, _user.tenant_id)
    # Prefer manual HiTL drawing; fall back to generated line_drawing.
    artifact = await _latest_artifact(
        db, item_id, _user.tenant_id, "hitl_drawing"
    ) or await _latest_artifact(
        db, item_id, _user.tenant_id, "line_drawing"
    )
    if artifact is None:
        return JSONResponse(
            status_code=404,
            content={
                "reason": "not_generated",
                "detail": "No line drawing available for this item yet.",
                "item_id": item_id,
            },
        )

    store = get_blob_store()
    try:
        data = await store.download(artifact.s3_key)
    except (FileNotFoundError, KeyError):
        return JSONResponse(
            status_code=404,
            content={
                "reason": "blob_missing",
                "detail": "Artifact row exists but the underlying blob is missing.",
                "artifact_id": artifact.id,
                "storage_key": artifact.s3_key,
            },
        )
    mime = artifact.mime_type or "image/svg+xml"
    filename = (artifact.s3_key or "").split("/")[-1] or "line_drawing.svg"
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Artifact-Id": artifact.id,
            "X-Content-Hash": artifact.content_hash or "",
        },
    )


@router.get("/{item_id}/bundle")
async def get_item_bundle(
    item_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return the printer-ready ZIP bundle for the item's parent order."""
    return await _stream_artifact(
        db, item_id, _user.tenant_id,
        artifact_type="bundle_zip",
        default_mime="application/zip",
    )


@router.get("/{item_id}/history", response_model=ItemHistoryResponse)
async def get_item_history(
    item_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ItemHistoryResponse:
    """Return a chronological state/audit log for an item.

    The history is assembled from two sources:

    1. ``AuditLog`` rows where ``resource_type='order_item'`` and
       ``resource_id=item_id`` — covers human-driven transitions.
    2. A synthetic "current state" entry from the item's own
       ``state_changed_at`` to ensure the UI always has *something* to
       render even if audit rows are absent.
    """
    item = await _load_item(db, item_id, _user.tenant_id)

    events: list[ItemHistoryEntry] = []

    # Synthetic "created" entry — anchor for the timeline.
    events.append(
        ItemHistoryEntry(
            step=1,
            at=(item.created_at or item.state_changed_at).isoformat() if item.created_at else item.state_changed_at.isoformat(),
            actor="system",
            actor_type="system",
            action="item_created",
            to_state="CREATED",
            detail=f"Item {item.item_no} created",
        )
    )

    # Audit log rows (tenant-scoped to be safe against misconfigured seeds).
    audit_rows = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.tenant_id == _user.tenant_id,
            AuditLog.resource_type == "order_item",
            AuditLog.resource_id == item_id,
        )
        .order_by(AuditLog.created_at.asc())
    )
    for i, row in enumerate(audit_rows.scalars().all(), start=2):
        details = row.details or {}
        events.append(
            ItemHistoryEntry(
                step=i,
                at=row.created_at.isoformat(),
                actor=row.actor or row.user_id,
                actor_type=row.actor_type,
                action=row.action,
                from_state=details.get("from_state"),
                to_state=details.get("to_state"),
                detail=row.detail,
            )
        )

    # If the item's current state differs from what the last audit row
    # reports, add a final synthetic step so the timeline lands on the
    # canonical `state`.
    last_to = events[-1].to_state if events else None
    if last_to != item.state:
        events.append(
            ItemHistoryEntry(
                step=len(events) + 1,
                at=item.state_changed_at.isoformat() if item.state_changed_at else "",
                actor="workflow",
                actor_type="agent",
                action="state_changed",
                from_state=last_to,
                to_state=item.state,
                detail="Latest known state",
            )
        )

    return ItemHistoryResponse(
        item_id=item.id,
        item_no=item.item_no,
        current_state=item.state,
        events=events,
    )
