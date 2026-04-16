"""Multi-channel notification dispatcher (TASK-038).

The dispatcher routes a :class:`NotificationSpec` to one or more
transports (email, Slack, PagerDuty, in-app DB), honors per-tenant
preferences, writes an audit log, and retries transports that raise
:class:`TransientFailure` with an exponential backoff.

Design
------
* **Swappable transports** — each channel implements the :class:`Transport`
  protocol. Tests inject fakes; production wires SMTP/SES, Slack webhooks,
  PagerDuty Events v2, and the in-app Notification table.
* **Pluggable preference store** — :class:`NotificationPreferenceStore`
  (``is_enabled(tenant_id, channel, event_type) -> bool``) decides
  whether a channel fires for a tenant. A default
  :class:`InMemoryPreferenceStore` allows all channels by default.
* **Retries** — configurable ``max_retries`` (default 3) with an
  exponential backoff starting at ``retry_base_seconds`` (default 0.5s).
  Only :class:`TransientFailure` triggers retry; other exceptions bubble
  immediately.
* **Audit** — every dispatch attempt (success *or* terminal failure)
  writes one :class:`AuditLog` row via the provided SQLAlchemy session
  factory; when no factory is configured, auditing is a no-op.
"""
from __future__ import annotations

import asyncio
import json
import smtplib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from enum import Enum
from typing import (
    Any,
    Awaitable,
    Callable,
    Iterable,
    Mapping,
    Optional,
    Protocol,
    runtime_checkable,
)

from labelforge.core.logging import get_logger
from labelforge.db.models import AuditLog, Notification as NotificationModel

_log = get_logger("labelforge.notifications")


# ── Domain types ─────────────────────────────────────────────────────────────


class Channel(str, Enum):
    EMAIL = "email"
    SLACK = "slack"
    PAGERDUTY = "pagerduty"
    IN_APP = "in_app"


class TransientFailure(Exception):
    """Raised by a transport when a dispatch may succeed on retry.

    Network timeouts, 5xx responses, SMTP ``4xx`` codes, etc. Any other
    exception from a transport is treated as permanent.
    """


@dataclass
class NotificationSpec:
    """Payload handed to the dispatcher.

    ``channels`` is the list of channels to attempt; the dispatcher will
    still filter through the preference store before calling any
    transport. ``data`` is free-form metadata that transports can pass
    through (e.g. PagerDuty ``details``).
    """

    tenant_id: str
    event_type: str
    title: str
    body: str
    channels: list[Channel]
    level: str = "info"                      # info | warning | error | critical
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    order_id: Optional[str] = None
    item_no: Optional[str] = None
    data: dict[str, Any] = field(default_factory=dict)


# ── Transport protocol ───────────────────────────────────────────────────────


@runtime_checkable
class Transport(Protocol):
    """All transports implement this async interface.

    Implementations *must* raise :class:`TransientFailure` for retryable
    errors. Anything else is treated as permanent.
    """

    channel: Channel

    async def send(self, spec: NotificationSpec) -> Mapping[str, Any]: ...


# ── Preferences ──────────────────────────────────────────────────────────────


@runtime_checkable
class NotificationPreferenceStore(Protocol):
    async def is_enabled(
        self, tenant_id: str, channel: Channel, event_type: str
    ) -> bool: ...


class InMemoryPreferenceStore:
    """Simple in-memory preference store.

    Default = enabled. Callers can ``set(tenant_id, channel, event_type,
    enabled=False)`` to mute a specific combination, or use
    ``mute_channel(tenant_id, channel)`` to mute an entire channel.
    """

    def __init__(self) -> None:
        self._overrides: dict[tuple[str, Channel, str], bool] = {}
        self._channel_mutes: dict[tuple[str, Channel], bool] = {}

    def set(
        self,
        tenant_id: str,
        channel: Channel,
        event_type: str,
        *,
        enabled: bool,
    ) -> None:
        self._overrides[(tenant_id, channel, event_type)] = enabled

    def mute_channel(self, tenant_id: str, channel: Channel) -> None:
        self._channel_mutes[(tenant_id, channel)] = True

    def unmute_channel(self, tenant_id: str, channel: Channel) -> None:
        self._channel_mutes.pop((tenant_id, channel), None)

    async def is_enabled(
        self, tenant_id: str, channel: Channel, event_type: str
    ) -> bool:
        explicit = self._overrides.get((tenant_id, channel, event_type))
        if explicit is not None:
            return explicit
        if self._channel_mutes.get((tenant_id, channel)):
            return False
        return True


# ── Built-in transports ──────────────────────────────────────────────────────


class EmailTransport:
    """Send via SMTP (or an injected ``sender`` callable for tests/SES).

    The ``sender`` callable receives a prepared :class:`email.message.EmailMessage`
    and may raise :class:`TransientFailure` on retryable errors.
    """

    channel = Channel.EMAIL

    def __init__(
        self,
        *,
        from_addr: str,
        host: str = "localhost",
        port: int = 25,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = False,
        sender: Optional[Callable[[EmailMessage], None]] = None,
    ) -> None:
        self.from_addr = from_addr
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self._sender = sender

    async def send(self, spec: NotificationSpec) -> Mapping[str, Any]:
        if not spec.user_email:
            # Missing recipient is a permanent failure — no point retrying.
            raise ValueError("EmailTransport requires spec.user_email")

        msg = EmailMessage()
        msg["From"] = self.from_addr
        msg["To"] = spec.user_email
        msg["Subject"] = f"[{spec.level.upper()}] {spec.title}"
        msg.set_content(spec.body)

        if self._sender is not None:
            # Synchronous callable; run in default executor so we don't
            # block the event loop when the caller uses real SMTP.
            await asyncio.to_thread(self._sender, msg)
            return {"to": spec.user_email}

        await asyncio.to_thread(self._smtp_send, msg)
        return {"to": spec.user_email, "host": self.host}

    def _smtp_send(self, msg: EmailMessage) -> None:
        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as client:
                if self.use_tls:
                    client.starttls()
                if self.username and self.password:
                    client.login(self.username, self.password)
                client.send_message(msg)
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, TimeoutError, OSError) as exc:
            raise TransientFailure(f"smtp transient: {exc}") from exc
        except smtplib.SMTPResponseException as exc:
            # 4xx = transient, 5xx = permanent.
            if 400 <= exc.smtp_code < 500:
                raise TransientFailure(f"smtp 4xx: {exc.smtp_code} {exc.smtp_error!r}") from exc
            raise


class SlackTransport:
    """Post to a Slack incoming webhook.

    HTTP ``5xx`` / ``429`` / network errors -> :class:`TransientFailure`.
    Any other ``4xx`` is permanent (bad webhook, malformed payload).
    """

    channel = Channel.SLACK

    def __init__(
        self,
        *,
        webhook_url: str,
        poster: Optional[Callable[[str, dict[str, Any]], Awaitable[int]]] = None,
    ) -> None:
        self.webhook_url = webhook_url
        self._poster = poster

    async def send(self, spec: NotificationSpec) -> Mapping[str, Any]:
        payload = self._build_payload(spec)
        status = await self._post(self.webhook_url, payload)
        if 500 <= status < 600 or status == 429:
            raise TransientFailure(f"slack transient: HTTP {status}")
        if status >= 400:
            raise RuntimeError(f"slack permanent: HTTP {status}")
        return {"webhook": self.webhook_url, "status": status}

    @staticmethod
    def _build_payload(spec: NotificationSpec) -> dict[str, Any]:
        return {
            "text": f"*[{spec.level.upper()}] {spec.title}*\n{spec.body}",
            "attachments": [
                {
                    "color": _slack_color_for(spec.level),
                    "fields": [
                        {"title": "event_type", "value": spec.event_type, "short": True},
                        {"title": "tenant_id", "value": spec.tenant_id, "short": True},
                    ]
                    + ([{"title": "order_id", "value": spec.order_id, "short": True}] if spec.order_id else []),
                }
            ],
        }

    async def _post(self, url: str, payload: dict[str, Any]) -> int:
        if self._poster is not None:
            return await self._poster(url, payload)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, json=payload)
                return int(resp.status_code)
        except httpx.TransportError as exc:  # type: ignore[attr-defined]
            raise TransientFailure(f"slack network: {exc}") from exc


def _slack_color_for(level: str) -> str:
    return {
        "critical": "#dc2626",
        "error": "#ef4444",
        "warning": "#f59e0b",
        "info": "#3b82f6",
    }.get(level, "#9ca3af")


class PagerDutyTransport:
    """PagerDuty Events API v2 (``enqueue`` event_action=trigger).

    5xx / 429 / network -> transient; 4xx -> permanent.
    """

    channel = Channel.PAGERDUTY
    DEFAULT_URL = "https://events.pagerduty.com/v2/enqueue"

    def __init__(
        self,
        *,
        integration_key: str,
        source: str = "labelforge",
        url: Optional[str] = None,
        poster: Optional[Callable[[str, dict[str, Any]], Awaitable[int]]] = None,
    ) -> None:
        self.integration_key = integration_key
        self.source = source
        self.url = url or self.DEFAULT_URL
        self._poster = poster

    async def send(self, spec: NotificationSpec) -> Mapping[str, Any]:
        payload = {
            "routing_key": self.integration_key,
            "event_action": "trigger",
            "dedup_key": f"{spec.tenant_id}:{spec.event_type}:{spec.order_id or ''}",
            "payload": {
                "summary": spec.title,
                "source": self.source,
                "severity": _pagerduty_severity(spec.level),
                "component": spec.event_type,
                "custom_details": {
                    "body": spec.body,
                    "tenant_id": spec.tenant_id,
                    "user_id": spec.user_id,
                    "order_id": spec.order_id,
                    "item_no": spec.item_no,
                    **spec.data,
                },
            },
        }
        status = await self._post(self.url, payload)
        if 500 <= status < 600 or status == 429:
            raise TransientFailure(f"pagerduty transient: HTTP {status}")
        if status >= 400:
            raise RuntimeError(f"pagerduty permanent: HTTP {status}")
        return {"dedup_key": payload["dedup_key"], "status": status}

    async def _post(self, url: str, payload: dict[str, Any]) -> int:
        if self._poster is not None:
            return await self._poster(url, payload)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, json=payload)
                return int(resp.status_code)
        except httpx.TransportError as exc:  # type: ignore[attr-defined]
            raise TransientFailure(f"pagerduty network: {exc}") from exc


def _pagerduty_severity(level: str) -> str:
    return {
        "critical": "critical",
        "error": "error",
        "warning": "warning",
        "info": "info",
    }.get(level, "info")


class InAppTransport:
    """Persist an in-app notification row via an injected session factory.

    The session factory must return an object supporting ``async with ...
    as session:`` with ``session.add(...)`` + ``await session.commit()`` —
    i.e. :func:`sqlalchemy.ext.asyncio.async_sessionmaker`.
    """

    channel = Channel.IN_APP

    def __init__(
        self,
        *,
        session_factory: Callable[[], Any],
    ) -> None:
        self._session_factory = session_factory

    async def send(self, spec: NotificationSpec) -> Mapping[str, Any]:
        notif_id = uuid.uuid4().hex
        try:
            async with self._session_factory() as session:
                session.add(
                    NotificationModel(
                        id=notif_id,
                        tenant_id=spec.tenant_id,
                        user_id=spec.user_id,
                        type=spec.event_type,
                        title=spec.title,
                        body=spec.body,
                        level=spec.level,
                        order_id=spec.order_id,
                        item_no=spec.item_no,
                        is_read=False,
                    )
                )
                await session.commit()
        except Exception as exc:
            # DB-layer transient (connection reset, deadlock) is rare but
            # common enough that we expose it as transient so retries kick in.
            raise TransientFailure(f"in_app db error: {exc}") from exc
        return {"notification_id": notif_id}


# ── Dispatcher ───────────────────────────────────────────────────────────────


class NotificationDispatcher:
    """Route a :class:`NotificationSpec` across one or more transports.

    Parameters
    ----------
    transports:
        Iterable of :class:`Transport` implementations; the dispatcher
        selects the transport whose ``.channel`` matches each entry in
        ``spec.channels``.
    preferences:
        :class:`NotificationPreferenceStore`; defaults to
        :class:`InMemoryPreferenceStore` (all channels enabled).
    max_retries:
        Number of *additional* attempts after the first failure. Set to
        0 to disable retries. Defaults to 3.
    retry_base_seconds:
        Base delay for exponential backoff (``delay = base * 2**attempt``).
    audit_session_factory:
        Optional async_sessionmaker returning a DB session; when provided,
        every dispatch attempt writes an :class:`AuditLog` row. When
        ``None`` (the test default), auditing is skipped.
    sleep:
        Injectable async sleep for tests (defaults to :func:`asyncio.sleep`).
    """

    def __init__(
        self,
        *,
        transports: Iterable[Transport] = (),
        preferences: Optional[NotificationPreferenceStore] = None,
        max_retries: int = 3,
        retry_base_seconds: float = 0.5,
        audit_session_factory: Optional[Callable[[], Any]] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._transports: dict[Channel, Transport] = {t.channel: t for t in transports}
        self._preferences = preferences or InMemoryPreferenceStore()
        self._max_retries = max(0, int(max_retries))
        self._retry_base = max(0.0, float(retry_base_seconds))
        self._audit_session_factory = audit_session_factory
        self._sleep = sleep

    # ── Registration helpers ────────────────────────────────────────────────

    def register(self, transport: Transport) -> None:
        self._transports[transport.channel] = transport

    def channels(self) -> list[Channel]:
        return list(self._transports.keys())

    @property
    def preferences(self) -> NotificationPreferenceStore:
        return self._preferences

    # ── Main entry point ────────────────────────────────────────────────────

    async def dispatch(self, spec: NotificationSpec) -> dict[Channel, dict[str, Any]]:
        """Dispatch ``spec`` across every channel in ``spec.channels``.

        Returns a map ``{channel: {"status": "sent"|"muted"|"skipped"|"failed",
        "attempts": int, "detail": Mapping, "error": str|None}}``.
        Never raises — per-channel errors are captured in the result so
        callers can decide what to escalate.
        """
        results: dict[Channel, dict[str, Any]] = {}
        for channel in spec.channels:
            transport = self._transports.get(channel)
            if transport is None:
                results[channel] = {
                    "status": "skipped",
                    "attempts": 0,
                    "detail": {},
                    "error": "no transport registered",
                }
                await self._audit(spec, channel, results[channel])
                continue

            if not await self._preferences.is_enabled(spec.tenant_id, channel, spec.event_type):
                results[channel] = {
                    "status": "muted",
                    "attempts": 0,
                    "detail": {},
                    "error": None,
                }
                _log.info(
                    "notification.muted",
                    channel=channel.value,
                    tenant_id=spec.tenant_id,
                    event_type=spec.event_type,
                )
                await self._audit(spec, channel, results[channel])
                continue

            results[channel] = await self._send_with_retry(transport, spec)
            await self._audit(spec, channel, results[channel])

        return results

    # ── Internals ───────────────────────────────────────────────────────────

    async def _send_with_retry(
        self, transport: Transport, spec: NotificationSpec
    ) -> dict[str, Any]:
        last_exc: Optional[BaseException] = None
        for attempt in range(self._max_retries + 1):
            try:
                detail = await transport.send(spec)
                _log.info(
                    "notification.sent",
                    channel=transport.channel.value,
                    tenant_id=spec.tenant_id,
                    event_type=spec.event_type,
                    attempt=attempt + 1,
                )
                return {
                    "status": "sent",
                    "attempts": attempt + 1,
                    "detail": dict(detail),
                    "error": None,
                }
            except TransientFailure as exc:
                last_exc = exc
                _log.warning(
                    "notification.transient_failure",
                    channel=transport.channel.value,
                    tenant_id=spec.tenant_id,
                    event_type=spec.event_type,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                if attempt < self._max_retries:
                    delay = self._retry_base * (2 ** attempt)
                    await self._sleep(delay)
                    continue
                break
            except Exception as exc:  # noqa: BLE001 — permanent failures are captured
                _log.error(
                    "notification.permanent_failure",
                    channel=transport.channel.value,
                    tenant_id=spec.tenant_id,
                    event_type=spec.event_type,
                    error=str(exc),
                )
                return {
                    "status": "failed",
                    "attempts": attempt + 1,
                    "detail": {},
                    "error": str(exc),
                }

        return {
            "status": "failed",
            "attempts": self._max_retries + 1,
            "detail": {},
            "error": str(last_exc) if last_exc else "exhausted retries",
        }

    async def _audit(
        self,
        spec: NotificationSpec,
        channel: Channel,
        result: Mapping[str, Any],
    ) -> None:
        if self._audit_session_factory is None:
            return
        try:
            async with self._audit_session_factory() as session:
                session.add(
                    AuditLog(
                        id=uuid.uuid4().hex,
                        tenant_id=spec.tenant_id,
                        user_id=spec.user_id,
                        actor="notification_dispatcher",
                        actor_type="system",
                        action=f"notification.{result.get('status', 'unknown')}",
                        resource_type="notification",
                        resource_id=None,
                        detail=f"{channel.value}: {spec.event_type}",
                        details={
                            "channel": channel.value,
                            "event_type": spec.event_type,
                            "level": spec.level,
                            "attempts": result.get("attempts", 0),
                            "error": result.get("error"),
                            "title": spec.title,
                            "order_id": spec.order_id,
                        },
                    )
                )
                await session.commit()
        except Exception as exc:  # audit must never break dispatch
            _log.warning(
                "notification.audit_failed",
                channel=channel.value,
                error=str(exc),
            )


# ── Module singleton ─────────────────────────────────────────────────────────


_DISPATCHER: Optional[NotificationDispatcher] = None


def get_dispatcher() -> NotificationDispatcher:
    """Return the process-wide dispatcher, creating an empty one on first use."""
    global _DISPATCHER
    if _DISPATCHER is None:
        _DISPATCHER = NotificationDispatcher()
    return _DISPATCHER


def set_dispatcher(dispatcher: Optional[NotificationDispatcher]) -> None:
    """Install (or clear) the process-wide dispatcher."""
    global _DISPATCHER
    _DISPATCHER = dispatcher


__all__ = [
    "Channel",
    "EmailTransport",
    "InAppTransport",
    "InMemoryPreferenceStore",
    "NotificationDispatcher",
    "NotificationPreferenceStore",
    "NotificationSpec",
    "PagerDutyTransport",
    "SlackTransport",
    "TransientFailure",
    "Transport",
    "get_dispatcher",
    "set_dispatcher",
]
