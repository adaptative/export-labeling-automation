"""Importer & Printer Portal API (INT-017, Sprint-13).

External-facing endpoints for users who don't have a LabelForge account:

* **Importer portal** — reviews the order's approval PDF, approves or
  rejects the proposed labels.
* **Printer portal** — downloads the printer bundle, confirms receipt.

Auth is **opaque bearer tokens** (not JWT).  Ops generates a
:class:`PortalToken` row for a specific (order, role) pair; the URL
``/api/v1/portal/{role}/{token}`` is shared with the external user.
The token is single-use for its terminal action (approve / reject /
confirm) — subsequent attempts are rejected with 409.

Every portal action writes an :class:`AuditLog` row with
``actor_type='portal'`` and ``actor={email or token prefix}`` so a
compliance officer can reconstruct who approved what and when.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.api.v1.documents import get_blob_store
from labelforge.core.auth import TokenPayload
from labelforge.db.models import (
    Artifact, AuditLog, Importer, Order, OrderItemModel, PortalToken,
)
from labelforge.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["portal"])


# ── Request / response models ───────────────────────────────────────────────


class PortalTokenCreateRequest(BaseModel):
    order_id: str
    role: str = Field(..., description="importer | printer")
    email: Optional[str] = None
    expires_in_hours: int = Field(72, ge=1, le=24 * 30)


class PortalTokenResponse(BaseModel):
    token: str
    url_path: str
    role: str
    order_id: str
    status: str
    expires_at: Optional[datetime]
    created_at: datetime


class PortalSessionResponse(BaseModel):
    role: str
    status: str
    order: dict
    importer: dict
    items: list[dict]
    expires_at: Optional[datetime] = None
    action_taken_at: Optional[datetime] = None


class PortalApproveRequest(BaseModel):
    approver_name: Optional[str] = None
    approver_email: Optional[str] = None
    note: Optional[str] = None


class PortalRejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)
    reviewer_name: Optional[str] = None
    reviewer_email: Optional[str] = None


class PortalPrinterConfirmRequest(BaseModel):
    printer_name: Optional[str] = None
    printer_email: Optional[str] = None
    received_at: Optional[datetime] = None
    note: Optional[str] = None


class PortalActionResponse(BaseModel):
    ok: bool
    status: str
    order_id: str
    action_taken_at: datetime
    message: str


# ── Helpers ─────────────────────────────────────────────────────────────────


VALID_ROLES = {"importer", "printer"}


async def _load_token(
    db: AsyncSession, token: str, expected_role: Optional[str] = None,
) -> PortalToken:
    """Fetch a portal token by value. 404 if missing or role mismatch."""
    result = await db.execute(
        select(PortalToken).where(PortalToken.token == token)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Invalid portal token")
    if expected_role is not None and row.role != expected_role:
        raise HTTPException(status_code=404, detail="Invalid portal token")
    if row.expires_at:
        # SQLite strips tzinfo on read — normalize both sides to UTC-aware.
        exp = row.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Portal token expired")
    return row


def _assert_active(t: PortalToken) -> None:
    """409 if the token has already been used for its terminal action."""
    if t.status != "active":
        raise HTTPException(
            status_code=409,
            detail=f"Portal token already {t.status}",
        )


async def _load_session_payload(
    db: AsyncSession, token_row: PortalToken,
) -> PortalSessionResponse:
    """Build the read-only session view (order + items) for a portal page."""
    order = (
        await db.execute(select(Order).where(Order.id == token_row.order_id))
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order missing for token")

    importer = (
        await db.execute(select(Importer).where(Importer.id == order.importer_id))
    ).scalar_one_or_none()

    items_result = await db.execute(
        select(OrderItemModel).where(OrderItemModel.order_id == order.id)
    )
    items = items_result.scalars().all()

    return PortalSessionResponse(
        role=token_row.role,
        status=token_row.status,
        order={
            "id": order.id,
            "po_number": order.po_number,
            "external_ref": order.external_ref,
            "importer_id": order.importer_id,
            "item_count": len(items),
        },
        importer={
            "id": importer.id if importer else order.importer_id,
            "name": importer.name if importer else None,
            "code": importer.code if importer else None,
        },
        items=[
            {
                "id": it.id,
                "item_no": it.item_no,
                "state": it.state,
                "state_changed_at": it.state_changed_at.isoformat() if it.state_changed_at else None,
            }
            for it in items
        ],
        expires_at=token_row.expires_at,
        action_taken_at=token_row.action_taken_at,
    )


async def _audit(
    db: AsyncSession,
    *, tenant_id: str, action: str, resource_type: str,
    resource_id: Optional[str], actor: Optional[str],
    detail: Optional[str], details: Optional[dict] = None,
) -> None:
    """Write a portal audit log entry."""
    db.add(AuditLog(
        id=str(uuid4()),
        tenant_id=tenant_id,
        user_id=None,
        actor=actor or "portal",
        actor_type="portal",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        details=details or {},
    ))


# ── Ops-facing: generate tokens ─────────────────────────────────────────────


@router.post("/tokens", response_model=PortalTokenResponse, status_code=201)
async def create_portal_token(
    req: PortalTokenCreateRequest,
    user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortalTokenResponse:
    """Ops generates a single-use portal token for an importer or printer."""
    if req.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400, detail=f"role must be one of: {sorted(VALID_ROLES)}",
        )

    # Order must belong to the caller's tenant.
    order = (
        await db.execute(
            select(Order).where(
                Order.id == req.order_id,
                Order.tenant_id == user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    token_value = secrets.token_urlsafe(32)
    expires_at = (
        datetime.now(timezone.utc).replace(microsecond=0)
        + timedelta(hours=req.expires_in_hours)
    )

    row = PortalToken(
        id=str(uuid4()),
        token=token_value,
        tenant_id=user.tenant_id,
        order_id=req.order_id,
        role=req.role,
        email=req.email,
        expires_at=expires_at,
        created_by=user.user_id,
    )
    db.add(row)
    await _audit(
        db, tenant_id=user.tenant_id,
        action="portal_token_created",
        resource_type="order", resource_id=req.order_id,
        actor=user.user_id, detail=f"Created {req.role} portal token",
        details={"role": req.role, "email": req.email,
                 "token_prefix": token_value[:8]},
    )
    await db.commit()
    await db.refresh(row)

    return PortalTokenResponse(
        token=token_value,
        url_path=f"/api/v1/portal/{req.role}/{token_value}",
        role=req.role,
        order_id=req.order_id,
        status=row.status,
        expires_at=row.expires_at,
        created_at=row.created_at,
    )


# ── Importer portal ─────────────────────────────────────────────────────────


@router.get("/importer/{token}", response_model=PortalSessionResponse)
async def get_importer_session(
    token: str, db: AsyncSession = Depends(get_db),
) -> PortalSessionResponse:
    """Read-only view of the order + items pending importer review."""
    row = await _load_token(db, token, expected_role="importer")
    return await _load_session_payload(db, row)


@router.post("/importer/{token}/approve", response_model=PortalActionResponse)
async def importer_approve(
    token: str, req: PortalApproveRequest,
    db: AsyncSession = Depends(get_db),
) -> PortalActionResponse:
    """Importer approves the proposed labels — terminal action."""
    row = await _load_token(db, token, expected_role="importer")
    _assert_active(row)

    now = datetime.now(timezone.utc)
    row.status = "approved"
    row.action_taken_at = now
    row.note = req.note

    actor = req.approver_email or req.approver_name or (row.email or "importer-portal")
    await _audit(
        db, tenant_id=row.tenant_id,
        action="portal_importer_approved",
        resource_type="order", resource_id=row.order_id,
        actor=actor, detail="Importer approved via portal",
        details={
            "approver_name": req.approver_name,
            "approver_email": req.approver_email,
            "note": req.note,
            "token_prefix": row.token[:8],
        },
    )
    await db.commit()

    return PortalActionResponse(
        ok=True, status=row.status, order_id=row.order_id,
        action_taken_at=now, message="Approval recorded. Thank you!",
    )


@router.post("/importer/{token}/reject", response_model=PortalActionResponse)
async def importer_reject(
    token: str, req: PortalRejectRequest,
    db: AsyncSession = Depends(get_db),
) -> PortalActionResponse:
    """Importer rejects the proposed labels — must supply a reason."""
    row = await _load_token(db, token, expected_role="importer")
    _assert_active(row)

    now = datetime.now(timezone.utc)
    row.status = "rejected"
    row.action_taken_at = now
    row.note = req.reason

    actor = req.reviewer_email or req.reviewer_name or (row.email or "importer-portal")
    await _audit(
        db, tenant_id=row.tenant_id,
        action="portal_importer_rejected",
        resource_type="order", resource_id=row.order_id,
        actor=actor, detail="Importer rejected via portal",
        details={
            "reviewer_name": req.reviewer_name,
            "reviewer_email": req.reviewer_email,
            "reason": req.reason,
            "token_prefix": row.token[:8],
        },
    )
    await db.commit()

    return PortalActionResponse(
        ok=True, status=row.status, order_id=row.order_id,
        action_taken_at=now,
        message="Rejection recorded. Your ops contact has been notified.",
    )


# ── Printer portal ──────────────────────────────────────────────────────────


@router.get("/printer/{token}", response_model=PortalSessionResponse)
async def get_printer_session(
    token: str, db: AsyncSession = Depends(get_db),
) -> PortalSessionResponse:
    """Read-only view of the order + items ready for the printer to pull."""
    row = await _load_token(db, token, expected_role="printer")
    return await _load_session_payload(db, row)


@router.post("/printer/{token}/confirm", response_model=PortalActionResponse)
async def printer_confirm(
    token: str, req: PortalPrinterConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> PortalActionResponse:
    """Printer confirms receipt of the bundle — terminal action."""
    row = await _load_token(db, token, expected_role="printer")
    _assert_active(row)

    now = req.received_at or datetime.now(timezone.utc)
    row.status = "confirmed"
    row.action_taken_at = now
    row.note = req.note

    actor = req.printer_email or req.printer_name or (row.email or "printer-portal")
    await _audit(
        db, tenant_id=row.tenant_id,
        action="portal_printer_confirmed",
        resource_type="order", resource_id=row.order_id,
        actor=actor, detail="Printer confirmed receipt via portal",
        details={
            "printer_name": req.printer_name,
            "printer_email": req.printer_email,
            "received_at": now.isoformat(),
            "note": req.note,
            "token_prefix": row.token[:8],
        },
    )
    await db.commit()

    return PortalActionResponse(
        ok=True, status=row.status, order_id=row.order_id,
        action_taken_at=now,
        message="Receipt confirmed. Bundle is now delivered.",
    )


# ── Token-scoped bundle download (printer) ──────────────────────────────────


async def _latest_bundle_for_item(
    db: AsyncSession, item_id: str, tenant_id: str,
) -> Optional[Artifact]:
    """Return the newest bundle_zip artifact for a given item, or None."""
    result = await db.execute(
        select(Artifact)
        .where(
            Artifact.order_item_id == item_id,
            Artifact.tenant_id == tenant_id,
            Artifact.artifact_type == "bundle_zip",
        )
        .order_by(Artifact.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/printer/{token}/items/{item_id}/bundle")
async def get_printer_item_bundle(
    token: str, item_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Stream a printer-ready bundle ZIP for an item, authed by portal token.

    The printer portal does not issue JWTs; this endpoint accepts the opaque
    bearer token in the URL and validates three things in order:

    1. The token exists, is role=printer, and isn't expired.
    2. The requested item belongs to the token's order (prevents a printer
       from fishing bundles for orders they weren't issued a link for).
    3. A bundle artifact row exists and its blob is present.

    Returns the same structured-404 shape as :mod:`item_artifacts` so the
    UI can render a "not generated" state rather than crashing.
    """
    row = await _load_token(db, token, expected_role="printer")
    # Do NOT require `active` — allow re-download after confirm for reprints.

    item = (
        await db.execute(
            select(OrderItemModel).where(
                OrderItemModel.id == item_id,
                OrderItemModel.tenant_id == row.tenant_id,
                OrderItemModel.order_id == row.order_id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not in this order")

    artifact = await _latest_bundle_for_item(db, item_id, row.tenant_id)
    if artifact is None:
        return JSONResponse(
            status_code=404,
            content={
                "reason": "not_generated",
                "detail": "No bundle has been generated for this item yet.",
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
                "detail": "Bundle row exists but the ZIP is missing from storage.",
                "artifact_id": artifact.id,
                "storage_key": artifact.s3_key,
            },
        )

    # Light-touch audit — a download isn't a terminal action so we only log
    # it; status stays as-is so the operator can still confirm.
    await _audit(
        db, tenant_id=row.tenant_id,
        action="portal_printer_bundle_downloaded",
        resource_type="order_item", resource_id=item_id,
        actor=(row.email or "printer-portal"),
        detail="Printer downloaded bundle via portal",
        details={"token_prefix": row.token[:8], "artifact_id": artifact.id},
    )
    await db.commit()

    filename = (artifact.s3_key or "").split("/")[-1] or f"{item.item_no}_bundle.zip"
    return Response(
        content=data,
        media_type=artifact.mime_type or "application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Artifact-Id": artifact.id,
            "X-Content-Hash": artifact.content_hash or "",
        },
    )
