"""HiTL MessageRouter — realtime event fan-out between agents and humans.

Event shape
-----------
Every envelope published through the router is a JSON-serializable dict::

    {
        "type":       "agent_message" | "human_message" | "status_update"
                    | "escalation"    | "typing"        | "option_selected"
                    | "thread_resolved" | "ping",
        "thread_id":  "<HiTL thread UUID>",
        "payload":    {...},             # event-specific fields
        "ts":         "2026-04-16T12:34:56.789Z",
    }

Transport
---------
* :class:`RedisMessageRouter` — production: Redis ``PUBLISH`` / ``PSUBSCRIBE``
  with channel key ``hitl:thread:{thread_id}``. Cross-process fan-out so any
  API worker can publish and WebSocket workers anywhere in the fleet receive.
* :class:`InMemoryMessageRouter` — tests/dev: single-process ``asyncio.Queue``
  fan-out. Good enough for one worker and trivially deterministic in tests.

Subscribers call :meth:`MessageRouter.subscribe(thread_id)` and get an async
iterator of envelopes. The iterator terminates when :meth:`unsubscribe` is
called from the same coroutine (typical use-case: WebSocket disconnect).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Optional, Protocol, Set

logger = logging.getLogger(__name__)


# ── Event types (string constants — keep in sync with frontend) ────────────


class EventType:
    AGENT_MESSAGE = "agent_message"
    HUMAN_MESSAGE = "human_message"
    STATUS_UPDATE = "status_update"
    ESCALATION = "escalation"
    TYPING = "typing"
    OPTION_SELECTED = "option_selected"
    THREAD_RESOLVED = "thread_resolved"
    PING = "ping"


def _channel(thread_id: str) -> str:
    return f"hitl:thread:{thread_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_envelope(event_type: str, thread_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build a canonical event envelope."""
    return {
        "type": event_type,
        "thread_id": thread_id,
        "payload": payload,
        "ts": _now_iso(),
    }


# ── Protocol — what WebSocket / resolver depend on ─────────────────────────


class MessageRouter(Protocol):
    """Router interface.

    Implementations MUST provide the three async methods below. The exact
    transport (in-memory, Redis, etc.) is hidden behind this interface so
    the WebSocket endpoint and the ThreadResolver can be written once.
    """

    async def publish(self, thread_id: str, envelope: Dict[str, Any]) -> None: ...

    def subscribe(self, thread_id: str) -> "Subscription": ...

    async def aclose(self) -> None: ...


class Subscription:
    """Async iterator over envelopes for a single thread.

    Returned by :meth:`MessageRouter.subscribe`. Guarantees:

    * ``__aiter__`` yields dicts in publish order.
    * ``unsubscribe()`` closes the iterator — any in-flight ``__anext__``
      raises :class:`StopAsyncIteration`.
    * Idempotent unsubscribe (safe to call after close).
    """

    def __init__(self, queue: "asyncio.Queue[Optional[Dict[str, Any]]]",
                 unsubscribe_cb: Any) -> None:
        self._queue = queue
        self._unsubscribe_cb = unsubscribe_cb
        self._closed = False

    def __aiter__(self) -> "Subscription":
        return self

    async def __anext__(self) -> Dict[str, Any]:
        if self._closed:
            raise StopAsyncIteration
        item = await self._queue.get()
        if item is None:  # sentinel for close
            self._closed = True
            raise StopAsyncIteration
        return item

    async def unsubscribe(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._unsubscribe_cb()
        except Exception as exc:  # best-effort cleanup
            logger.debug("unsubscribe cleanup failed: %s", exc)
        # Push sentinel so any pending __anext__ returns promptly.
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass


# ── In-memory implementation ────────────────────────────────────────────────


class InMemoryMessageRouter:
    """Single-process ``asyncio.Queue`` fan-out router.

    Used in tests and single-worker dev. Each :meth:`subscribe` allocates
    a fresh queue; :meth:`publish` pushes to every queue registered for
    the thread. Queues are unbounded — callers are expected to drain
    promptly (WebSocket loops do).
    """

    def __init__(self) -> None:
        self._subs: Dict[str, Set["asyncio.Queue[Optional[Dict[str, Any]]]"]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, thread_id: str, envelope: Dict[str, Any]) -> None:
        async with self._lock:
            queues = list(self._subs.get(thread_id, ()))
        for q in queues:
            try:
                q.put_nowait(envelope)
            except asyncio.QueueFull:  # pragma: no cover — queues are unbounded
                logger.warning("router queue full for thread=%s, dropping event", thread_id)

    def subscribe(self, thread_id: str) -> Subscription:
        queue: "asyncio.Queue[Optional[Dict[str, Any]]]" = asyncio.Queue()

        # Register synchronously so no events are missed between subscribe
        # and the caller starting to iterate. Lock acquisition for the set
        # mutation is async, so we schedule it but also add eagerly with a
        # lightweight fallback — the lock only protects concurrent writes.
        bucket = self._subs.setdefault(thread_id, set())
        bucket.add(queue)

        async def _unsubscribe() -> None:
            async with self._lock:
                bucket_inner = self._subs.get(thread_id)
                if bucket_inner and queue in bucket_inner:
                    bucket_inner.discard(queue)
                if bucket_inner is not None and not bucket_inner:
                    self._subs.pop(thread_id, None)

        return Subscription(queue, _unsubscribe)

    def subscriber_count(self, thread_id: str) -> int:
        return len(self._subs.get(thread_id, ()))

    async def aclose(self) -> None:
        """Sever all subscriptions — used during shutdown."""
        async with self._lock:
            threads = list(self._subs.items())
            self._subs.clear()
        for _thread, queues in threads:
            for q in queues:
                try:
                    q.put_nowait(None)
                except Exception:
                    pass


# ── Redis implementation ────────────────────────────────────────────────────


class RedisMessageRouter:
    """Redis pub/sub router.

    Uses a single long-lived ``redis.asyncio`` connection plus a dedicated
    ``PubSub`` per subscription. Envelopes are JSON-encoded on the wire.

    The implementation runs a background task per subscription that reads
    from ``pubsub.listen()`` and pushes into the local ``asyncio.Queue``
    exposed to the caller — this keeps the Subscription interface identical
    to the in-memory variant.
    """

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client
        self._tasks: Set[asyncio.Task[None]] = set()

    async def publish(self, thread_id: str, envelope: Dict[str, Any]) -> None:
        try:
            await self._redis.publish(_channel(thread_id), json.dumps(envelope))
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("redis publish failed for thread=%s: %s", thread_id, exc)

    def subscribe(self, thread_id: str) -> Subscription:
        queue: "asyncio.Queue[Optional[Dict[str, Any]]]" = asyncio.Queue()
        pubsub = self._redis.pubsub()
        stopped = asyncio.Event()

        async def _reader() -> None:
            try:
                await pubsub.subscribe(_channel(thread_id))
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning("redis subscribe failed: %s", exc)
                queue.put_nowait(None)
                return

            try:
                while not stopped.is_set():
                    try:
                        msg = await pubsub.get_message(
                            ignore_subscribe_messages=True, timeout=1.0
                        )
                    except Exception as exc:  # pragma: no cover
                        logger.debug("redis get_message error: %s", exc)
                        await asyncio.sleep(0.1)
                        continue
                    if msg is None:
                        continue
                    data = msg.get("data")
                    if isinstance(data, bytes):
                        data = data.decode()
                    if not data:
                        continue
                    try:
                        queue.put_nowait(json.loads(data))
                    except json.JSONDecodeError:
                        logger.warning("malformed router payload: %r", data)
            finally:
                try:
                    await pubsub.unsubscribe(_channel(thread_id))
                    await pubsub.aclose()
                except Exception:  # pragma: no cover
                    pass
                queue.put_nowait(None)

        task = asyncio.create_task(_reader())
        self._tasks.add(task)
        task.add_done_callback(lambda t: self._tasks.discard(t))

        async def _unsubscribe() -> None:
            stopped.set()

        return Subscription(queue, _unsubscribe)

    async def aclose(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()


# ── Module-level singleton — swappable for tests ────────────────────────────


_router: Optional[MessageRouter] = None


def get_message_router() -> MessageRouter:
    """Return the active router, lazily creating an in-memory one on first use.

    Production code wires a :class:`RedisMessageRouter` at FastAPI lifespan
    startup via :func:`set_message_router`. Tests may also inject stubs.
    """
    global _router
    if _router is None:
        _router = InMemoryMessageRouter()
    return _router


def set_message_router(router: Optional[MessageRouter]) -> None:
    """Install a router (or ``None`` to reset to lazy default)."""
    global _router
    _router = router
