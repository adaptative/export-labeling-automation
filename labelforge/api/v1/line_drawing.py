"""Line Drawing API (TASK-027).

FastAPI routes that back the HiTL manual-drawing canvas.  The heavy
lifting (validation, SVG rendering, connection manager) lives in
:mod:`labelforge.core.line_drawing` — this module is only the thin
transport layer that wires the canvas into the WebSocket pipe and
persists the finished SVG as an :class:`Artifact` + HiTL message.

Routes
------
* ``WS   /hitl/threads/{thread_id}/drawing/ws``    — realtime stroke pipe
* ``POST /hitl/threads/{thread_id}/drawing``       — finalize + attach SVG
* ``GET  /hitl/threads/{thread_id}/drawing``       — latest canvas snapshot
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.api.v1.documents import get_blob_store
from labelforge.config import settings
from labelforge.core.auth import AuthError, TokenPayload, decode_token
from labelforge.core.line_drawing import (
    DrawingValidationError,
    drawing_manager,
    strokes_to_svg,
    validate_stroke,
)
from labelforge.db.models import (
    Artifact,
    HiTLMessageModel,
    HiTLThreadModel,
    OrderItemModel,
)
from labelforge.db import session as _session_mod
from labelforge.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hitl", tags=["hitl-drawing"])


# ── Request / response models ───────────────────────────────────────────────


class FinalizeDrawingResponse(BaseModel):
    artifact_id: Optional[str] = Field(
        None, description="ID of the persisted Artifact row, if one was created"
    )
    message_id: str = Field(..., description="HiTL message recording the drawing")
    svg_key: str = Field(..., description="Blob-store key where the SVG lives")
    stroke_count: int = Field(..., ge=0)
    content_hash: str = Field(..., description="SHA-256 of the SVG bytes")


class DrawingSnapshotResponse(BaseModel):
    thread_id: str
    canvas_width: int
    canvas_height: int
    stroke_count: int
    strokes: list[dict]


# ── Helpers ─────────────────────────────────────────────────────────────────


async def _load_thread(
    db: AsyncSession, thread_id: str, tenant_id: str
) -> HiTLThreadModel:
    result = await db.execute(
        select(HiTLThreadModel).where(
            HiTLThreadModel.id == thread_id,
            HiTLThreadModel.tenant_id == tenant_id,
        )
    )
    thread = result.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


async def _resolve_order_item_id(
    db: AsyncSession, tenant_id: str, order_id: str, item_no: str
) -> Optional[str]:
    """Look up the OrderItem row for the thread — required for Artifact FK."""
    result = await db.execute(
        select(OrderItemModel.id).where(
            OrderItemModel.tenant_id == tenant_id,
            OrderItemModel.order_id == order_id,
            OrderItemModel.item_no == item_no,
        )
    )
    return result.scalar_one_or_none()


# ── WebSocket ───────────────────────────────────────────────────────────────


@router.websocket("/threads/{thread_id}/drawing/ws")
async def drawing_websocket(
    websocket: WebSocket,
    thread_id: str,
    token: Optional[str] = Query(None, description="JWT; query-param for WS auth"),
) -> None:
    """Realtime stroke pipe.

    The client opens ``ws://…/api/v1/hitl/threads/{id}/drawing/ws?token=JWT``
    and receives a ``hello`` frame with the replay buffer.  It then sends
    ``{"type": "stroke", "stroke": {...}}`` messages which are validated
    and rebroadcast to every other peer in the same room.  Control frames:

    * ``{"type": "clear"}`` — wipe the session buffer and notify peers.
    * ``{"type": "ping"}``  — returns ``{"type": "pong"}`` for liveness.
    """
    if not token:
        await websocket.close(code=4401)
        return
    try:
        payload = decode_token(token, settings.jwt_secret_key)
    except AuthError:
        await websocket.close(code=4401)
        return

    # Tenant-scope the thread lookup before accepting the connection.
    async with _session_mod.async_session_factory() as db:
        result = await db.execute(
            select(HiTLThreadModel).where(
                HiTLThreadModel.id == thread_id,
                HiTLThreadModel.tenant_id == payload.tenant_id,
            )
        )
        if result.scalar_one_or_none() is None:
            await websocket.close(code=4404)
            return

    await websocket.accept()
    session = await drawing_manager.connect(thread_id, websocket)

    try:
        await websocket.send_json({"type": "hello", **session.snapshot()})

        while True:
            try:
                msg = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            except Exception:  # malformed frame — ignore, don't kill the socket
                await websocket.send_json(
                    {"type": "error", "detail": "invalid frame"}
                )
                continue

            kind = msg.get("type") if isinstance(msg, dict) else None

            if kind == "stroke":
                try:
                    stroke = validate_stroke(msg.get("stroke"))
                except DrawingValidationError as exc:
                    await websocket.send_json(
                        {"type": "error", "detail": str(exc)}
                    )
                    continue
                try:
                    session.add_stroke(stroke)
                except DrawingValidationError as exc:
                    await websocket.send_json(
                        {"type": "error", "detail": str(exc)}
                    )
                    continue
                await drawing_manager.broadcast(
                    thread_id,
                    {
                        "type": "stroke",
                        "stroke": stroke.to_dict(),
                        "user_id": payload.user_id,
                    },
                    exclude=websocket,
                )
            elif kind == "clear":
                session.clear()
                await drawing_manager.broadcast(
                    thread_id,
                    {"type": "clear", "user_id": payload.user_id},
                )
            elif kind == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json(
                    {"type": "error", "detail": f"unknown frame type: {kind!r}"}
                )
    finally:
        await drawing_manager.disconnect(thread_id, websocket)


# ── REST ────────────────────────────────────────────────────────────────────


@router.get(
    "/threads/{thread_id}/drawing", response_model=DrawingSnapshotResponse
)
async def get_drawing(
    thread_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DrawingSnapshotResponse:
    """Return the current in-memory canvas state for late joiners."""
    await _load_thread(db, thread_id, _user.tenant_id)
    snap = drawing_manager.session_for(thread_id).snapshot()
    return DrawingSnapshotResponse(**snap)


@router.post(
    "/threads/{thread_id}/drawing",
    response_model=FinalizeDrawingResponse,
    status_code=201,
)
async def finalize_drawing(
    thread_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FinalizeDrawingResponse:
    """Flatten the current session into an SVG blob + HiTL message + artifact."""
    thread = await _load_thread(db, thread_id, _user.tenant_id)
    session = drawing_manager.session_for(thread_id)
    if not session.strokes:
        raise HTTPException(status_code=409, detail="No strokes to finalize")

    svg_text = strokes_to_svg(
        session.strokes,
        width=session.canvas_width,
        height=session.canvas_height,
    )
    svg_bytes = svg_text.encode("utf-8")
    content_hash = hashlib.sha256(svg_bytes).hexdigest()
    svg_key = f"hitl-drawings/{thread_id}/{uuid4()}.svg"

    store = get_blob_store()
    await store.upload(svg_key, svg_bytes, content_type="image/svg+xml")

    artifact_id: Optional[str] = None
    order_item_id = await _resolve_order_item_id(
        db, _user.tenant_id, thread.order_id, thread.item_no
    )
    if order_item_id is not None:
        artifact = Artifact(
            id=str(uuid4()),
            tenant_id=_user.tenant_id,
            order_item_id=order_item_id,
            artifact_type="hitl_drawing",
            s3_key=svg_key,
            content_hash=content_hash,
            size_bytes=len(svg_bytes),
            mime_type="image/svg+xml",
            provenance={
                "thread_id": thread_id,
                "author_id": _user.user_id,
                "stroke_count": len(session.strokes),
            },
        )
        db.add(artifact)
        await db.flush()
        artifact_id = artifact.id
    else:
        logger.info(
            "Drawing finalized without OrderItem match (order=%s item=%s) — "
            "skipping artifact row",
            thread.order_id,
            thread.item_no,
        )

    message = HiTLMessageModel(
        id=str(uuid4()),
        thread_id=thread_id,
        tenant_id=_user.tenant_id,
        sender_type="drawing",
        content="Manual drawing attached",
        context={
            "svg_key": svg_key,
            "artifact_id": artifact_id,
            "stroke_count": len(session.strokes),
            "content_hash": content_hash,
        },
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    return FinalizeDrawingResponse(
        artifact_id=artifact_id,
        message_id=message.id,
        svg_key=svg_key,
        stroke_count=len(session.strokes),
        content_hash=content_hash,
    )
