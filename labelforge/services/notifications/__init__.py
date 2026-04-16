"""Notification dispatch service (TASK-038)."""
from __future__ import annotations

from labelforge.services.notifications.dispatcher import (
    Channel,
    EmailTransport,
    InAppTransport,
    InMemoryPreferenceStore,
    NotificationDispatcher,
    NotificationPreferenceStore,
    NotificationSpec,
    PagerDutyTransport,
    SlackTransport,
    TransientFailure,
    Transport,
    get_dispatcher,
    set_dispatcher,
)

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
