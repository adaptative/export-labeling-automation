"""Notification endpoints — list, mark-read, preferences, live WebSocket.

Sprint-15 additions (INT-023):
* ``PUT /notifications/{id}/read`` and ``PUT /notifications/read-all``
* ``GET /users/me/notification-preferences``
* ``PUT /users/me/notification-preferences``
* ``WebSocket /notifications/live`` — real-time fan-out of new notifications
  to the authenticated user via the shared HiTL Redis message router (same
  in-memory fallback for tests/dev).

Preferences are stored in-process per-tenant by reusing the dispatcher's
:class:`InMemoryPreferenceStore`. Tests & dev therefore see identical
behavior; production can swap in a DB-backed store via
:func:`set_dispatcher`.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.config import settings
from labelforge.core.auth import AuthError, TokenPayload, decode_token
from labelforge.db.models import Notification as NotificationModel
from labelforge.db.session import get_db
from labelforge.services.hitl import get_message_router
from labelforge.services.notifications import (
    Channel,
    InMemoryPreferenceStore,
    get_dispatcher,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])

# All known event types the UI can mute. Kept here so the settings page
# and the preferences response stay in sync.
KNOWN_EVENT_TYPES = [
    "cost_breaker.triggered",
    "hitl.escalated",
    "hitl.sla_breached",
    "order.completed",
    "order.failed",
    "pipeline.failure",
    "importer.invited",
    "system.alert",
]

KNOWN_CHANNELS = [c.value for c in Channel]

# Redis pub/sub channel for per-user notification fan-out.
USER_NOTIFICATION_CHANNEL = "notif:user:{user_id}"


# ── Response models ──────────────────────────────────────────────────────────


class Notification(BaseModel):
    id: str
    type: str
    title: str
    message: str
    severity: str
    order_id: Optional[str] = None
    item_no: Optional[str] = None
    read: bool = False
    created_at: datetime


class NotificationListResponse(BaseModel):
    notifications: list[Notification]
    total: int
    unread_count: int


class MarkReadResponse(BaseModel):
    id: str
    read: bool = True


class MarkAllReadResponse(BaseModel):
    marked: int


class ChannelPref(BaseModel):
    email: bool = True
    slack: bool = True
    pagerduty: bool = True
    in_app: bool = True


class EventPreference(BaseModel):
    event_type: str
    enabled: bool = True
    channels: ChannelPref = Field(default_factory=ChannelPref)


class NotificationPreferencesResponse(BaseModel):
    event_types: list[str]
    channels: list[str]
    preferences: list[EventPreference]


class UpdatePreferencesRequest(BaseModel):
    preferences: list[EventPreference]


# ── Helpers ─────────────────────────────────────────────────────────────────


def _to_notification(n: NotificationModel) -> Notification:
    return Notification(
        id=n.id,
        type=n.type,
        title=n.title,
        message=n.body or "",
        severity=n.level,
        order_id=n.order_id,
        item_no=n.item_no,
        read=n.is_read,
        created_at=n.created_at,
    )


def _tenant_scope(stmt, user: TokenPayload):
    """Apply tenant_id + user_id scoping so callers only see their rows."""
    return stmt.where(NotificationModel.tenant_id == user.tenant_id)


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    severity: Optional[str] = Query(None, description="Filter by severity: high, medium, low, info"),
    read: Optional[bool] = Query(None, description="Filter by read status"),
    order_id: Optional[str] = Query(None, description="Filter by order ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationListResponse:
    """List notifications with optional filtering."""
    query = _tenant_scope(select(NotificationModel), user)
    count_query = _tenant_scope(select(func.count()).select_from(NotificationModel), user)
    unread_query = _tenant_scope(
        select(func.count()).select_from(NotificationModel), user
    ).where(NotificationModel.is_read == False)  # noqa: E712

    if severity:
        query = query.where(NotificationModel.level == severity)
        count_query = count_query.where(NotificationModel.level == severity)
        unread_query = unread_query.where(NotificationModel.level == severity)

    if read is not None:
        query = query.where(NotificationModel.is_read == read)
        count_query = count_query.where(NotificationModel.is_read == read)

    if order_id:
        query = query.where(NotificationModel.order_id == order_id)
        count_query = count_query.where(NotificationModel.order_id == order_id)
        unread_query = unread_query.where(NotificationModel.order_id == order_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    unread_result = await db.execute(unread_query)
    unread_count = unread_result.scalar_one()

    query = query.order_by(NotificationModel.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    notifications = result.scalars().all()

    return NotificationListResponse(
        notifications=[_to_notification(n) for n in notifications],
        total=total,
        unread_count=unread_count,
    )


@router.put("/{notification_id}/read", response_model=MarkReadResponse)
async def mark_read(
    notification_id: str,
    user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarkReadResponse:
    """Mark a single notification as read."""
    row = (
        await db.execute(
            _tenant_scope(select(NotificationModel), user).where(
                NotificationModel.id == notification_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="notification not found")
    if not row.is_read:
        row.is_read = True
        await db.commit()
    return MarkReadResponse(id=notification_id, read=True)


@router.put("/read-all", response_model=MarkAllReadResponse)
async def mark_all_read(
    user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarkAllReadResponse:
    """Mark every unread notification for the caller's tenant as read."""
    stmt = (
        update(NotificationModel)
        .where(NotificationModel.tenant_id == user.tenant_id)
        .where(NotificationModel.is_read == False)  # noqa: E712
        .values(is_read=True)
    )
    result = await db.execute(stmt)
    await db.commit()
    return MarkAllReadResponse(marked=int(result.rowcount or 0))


# ── Preferences ──────────────────────────────────────────────────────────────
#
# We expose a "flat" preference model (event_type + per-channel on/off) so
# the frontend settings page stays simple. Internally, we translate each
# muted combination into the dispatcher's channel+event override.


users_router = APIRouter(prefix="/users", tags=["notifications"])


@users_router.get("/me/notification-preferences", response_model=NotificationPreferencesResponse)
async def get_notification_preferences(
    user: TokenPayload = Depends(get_current_user),
) -> NotificationPreferencesResponse:
    dispatcher = get_dispatcher()
    prefs = dispatcher.preferences
    payload: list[EventPreference] = []

    for event_type in KNOWN_EVENT_TYPES:
        channel_flags: dict[str, bool] = {}
        any_enabled = False
        for channel in Channel:
            is_on = True
            if isinstance(prefs, InMemoryPreferenceStore):
                is_on = await prefs.is_enabled(user.tenant_id, channel, event_type)
            else:
                is_on = await prefs.is_enabled(user.tenant_id, channel, event_type)
            channel_flags[channel.value] = is_on
            any_enabled = any_enabled or is_on
        payload.append(
            EventPreference(
                event_type=event_type,
                enabled=any_enabled,
                channels=ChannelPref(**channel_flags),
            )
        )

    return NotificationPreferencesResponse(
        event_types=list(KNOWN_EVENT_TYPES),
        channels=list(KNOWN_CHANNELS),
        preferences=payload,
    )


@users_router.put("/me/notification-preferences", response_model=NotificationPreferencesResponse)
async def update_notification_preferences(
    body: UpdatePreferencesRequest,
    user: TokenPayload = Depends(get_current_user),
) -> NotificationPreferencesResponse:
    dispatcher = get_dispatcher()
    prefs = dispatcher.preferences

    if not isinstance(prefs, InMemoryPreferenceStore):
        # For non-default stores, preferences are managed externally.
        raise HTTPException(status_code=501, detail="preference store is read-only")

    for pref in body.preferences:
        channels = pref.channels
        # "enabled=false" at the event level implies all channels off.
        if not pref.enabled:
            for channel in Channel:
                prefs.set(user.tenant_id, channel, pref.event_type, enabled=False)
            continue
        # Otherwise write per-channel overrides.
        pref_map = {
            Channel.EMAIL: channels.email,
            Channel.SLACK: channels.slack,
            Channel.PAGERDUTY: channels.pagerduty,
            Channel.IN_APP: channels.in_app,
        }
        for channel, enabled in pref_map.items():
            prefs.set(user.tenant_id, channel, pref.event_type, enabled=enabled)

    return await get_notification_preferences(user)


# ── WebSocket: /notifications/live ──────────────────────────────────────────


HEARTBEAT_SECONDS: float = 30.0


async def _recv_loop(ws: WebSocket) -> None:
    """Swallow incoming frames (only ``ping`` gets a reply)."""
    while True:
        raw = await ws.receive_text()
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if msg.get("type") == "ping":
            await ws.send_json({"type": "pong", "ts": datetime.now(timezone.utc).isoformat()})


async def _fan_out_loop(ws: WebSocket, subscription) -> None:
    async for envelope in subscription:
        if envelope is None:
            return
        await ws.send_json(envelope)


async def _heartbeat_loop(ws: WebSocket) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        await ws.send_json({"type": "heartbeat", "ts": datetime.now(timezone.utc).isoformat()})


@router.websocket("/live")
async def notifications_live(ws: WebSocket) -> None:
    """Real-time notification stream scoped to the authenticated user.

    Auth: ``?token=<jwt>`` query param (same pattern as
    ``/api/v1/hitl/threads/{id}/live``).

    The server broadcasts envelopes ``{type, payload, ts}`` where ``type``
    is one of ``notification_received``, ``notification_read``, ``heartbeat``,
    ``pong``.
    """
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=4401)
        return

    try:
        user = decode_token(token, settings.jwt_secret_key)
    except AuthError:
        await ws.close(code=4401)
        return

    router_obj = get_message_router()
    channel = USER_NOTIFICATION_CHANNEL.format(user_id=user.user_id)
    subscription = router_obj.subscribe(channel)

    await ws.accept()
    await ws.send_json({
        "type": "hello",
        "payload": {"user_id": user.user_id, "tenant_id": user.tenant_id},
        "ts": datetime.now(timezone.utc).isoformat(),
    })

    tasks = [
        asyncio.create_task(_recv_loop(ws), name="notif.recv"),
        asyncio.create_task(_fan_out_loop(ws, subscription), name="notif.fanout"),
        asyncio.create_task(_heartbeat_loop(ws), name="notif.heartbeat"),
    ]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                raise exc
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await subscription.unsubscribe()
        try:
            await ws.close()
        except Exception:
            pass
