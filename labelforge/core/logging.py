"""Structured logging (TASK-039).

All logging in labelforge is routed through structlog, which renders a
single JSON object per line. The following context keys are attached
automatically when present:

    tenant_id, request_id, user_id, agent_id, workflow_id

Public surface
--------------

* ``configure_logging(level=...)`` — call once at startup.
* ``get_logger(name)`` — returns a bound ``structlog.BoundLogger``.
* ``bind_context(**kwargs)`` / ``clear_context()`` — mutate the
  ContextVar-backed request-scoped dict.
* ``RequestLoggingMiddleware`` — ASGI middleware that binds ``request_id``
  and logs request/response with duration.
* ``log_agent_activity(agent_id)`` — decorator for agent entry points
  that binds ``agent_id`` and logs start/end/error.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from functools import wraps
from typing import Any, Awaitable, Callable, Mapping, MutableMapping, Optional, TypeVar, cast

import structlog


# ── Context variable ─────────────────────────────────────────────────────────
#
# A single ContextVar holding a dict. Using one dict rather than one
# ContextVar per field keeps ``bind_context`` / ``clear_context`` cheap
# and makes it trivial to capture a snapshot.

_LOG_CONTEXT: ContextVar[dict[str, Any]] = ContextVar("labelforge_log_context", default={})

# Canonical ordering for known context keys (helps reading JSON logs).
_CONTEXT_KEYS = ("tenant_id", "request_id", "user_id", "agent_id", "workflow_id")


def get_context() -> Mapping[str, Any]:
    """Return a copy of the current logging context."""
    return dict(_LOG_CONTEXT.get())


def bind_context(**values: Any) -> None:
    """Merge ``values`` into the current logging context.

    ``None`` values are dropped (use :func:`clear_context` to remove a key).
    """
    current = dict(_LOG_CONTEXT.get())
    for key, val in values.items():
        if val is None:
            current.pop(key, None)
        else:
            current[key] = val
    _LOG_CONTEXT.set(current)


def clear_context(*keys: str) -> None:
    """Remove ``keys`` from the context; if none given, clear everything."""
    if not keys:
        _LOG_CONTEXT.set({})
        return
    current = dict(_LOG_CONTEXT.get())
    for key in keys:
        current.pop(key, None)
    _LOG_CONTEXT.set(current)


def _merge_context_processor(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor that merges the ContextVar into every event."""
    ctx = _LOG_CONTEXT.get()
    if ctx:
        for key in _CONTEXT_KEYS:
            if key in ctx and key not in event_dict:
                event_dict[key] = ctx[key]
        # Any extra keys (e.g. custom bindings) go in too.
        for key, val in ctx.items():
            if key not in _CONTEXT_KEYS and key not in event_dict:
                event_dict[key] = val
    return event_dict


# ── Configuration ────────────────────────────────────────────────────────────


_CONFIGURED = False


def configure_logging(level: str | int | None = None) -> None:
    """Configure structlog + stdlib logging for JSON output.

    Safe to call multiple times; subsequent calls update the level but
    do not re-install processors.
    """
    global _CONFIGURED

    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")
    if isinstance(level, str):
        level = logging.getLevelName(level.upper())
    if not isinstance(level, int):
        level = logging.INFO

    # stdlib handler — every record routed through structlog's JSON renderer.
    root = logging.getLogger()
    root.setLevel(level)

    if not _CONFIGURED:
        # Remove any pre-existing handlers the app created via basicConfig.
        for handler in list(root.handlers):
            root.removeHandler(handler)

        handler = logging.StreamHandler(stream=sys.stdout)
        formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=[
                structlog.contextvars.merge_contextvars,
                _merge_context_processor,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
            ],
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)

        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                _merge_context_processor,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger. Lazy-configures if needed."""
    if not _CONFIGURED:
        configure_logging()
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


# ── ASGI request middleware ──────────────────────────────────────────────────


class RequestLoggingMiddleware:
    """ASGI middleware that attaches a request_id and logs every request.

    * Generates/propagates ``X-Request-ID`` header.
    * Binds ``request_id`` (and, when decodable, ``tenant_id`` + ``user_id``)
      to the logging context for the life of the request.
    * Emits ``request.start`` / ``request.end`` events with the status
      and elapsed time in ms.
    """

    def __init__(self, app: Any, logger_name: str = "labelforge.request") -> None:
        self.app = app
        self._logger = get_logger(logger_name)

    async def __call__(self, scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        incoming_id = headers.get(b"x-request-id", b"").decode() or None
        request_id = incoming_id or uuid.uuid4().hex

        # Token so we can restore the previous context on exit.
        token = _LOG_CONTEXT.set({**_LOG_CONTEXT.get(), "request_id": request_id})

        method = scope.get("method", "WS").upper() if scope["type"] == "http" else "WS"
        path = scope.get("path", "")
        start = time.perf_counter()
        status_holder: dict[str, int] = {}

        self._logger.info("request.start", method=method, path=path)

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = int(message.get("status", 0))
                # Echo request id in response headers for correlation.
                raw_headers = list(message.get("headers") or [])
                raw_headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = raw_headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            self._logger.exception(
                "request.error",
                method=method,
                path=path,
                duration_ms=elapsed_ms,
                error=str(exc),
            )
            raise
        else:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            self._logger.info(
                "request.end",
                method=method,
                path=path,
                status=status_holder.get("status"),
                duration_ms=elapsed_ms,
            )
        finally:
            _LOG_CONTEXT.reset(token)


# ── Agent activity decorator ─────────────────────────────────────────────────


F = TypeVar("F", bound=Callable[..., Any])


def log_agent_activity(
    agent_id: str,
    *,
    activity: Optional[str] = None,
    logger_name: str = "labelforge.agent",
) -> Callable[[F], F]:
    """Decorator that binds ``agent_id`` (and the fn name as activity) to
    the logging context for the lifetime of one call, logs start/end/error,
    and restores the prior context on exit.

    Works for both sync and async callables. The decorated callable's
    ``agent_id`` attribute is set to the bound id so callers can introspect.
    """

    def decorator(fn: F) -> F:
        act_name = activity or fn.__name__
        logger = get_logger(logger_name)

        if asyncio.iscoroutinefunction(fn):

            @wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                token = _LOG_CONTEXT.set(
                    {**_LOG_CONTEXT.get(), "agent_id": agent_id}
                )
                start = time.perf_counter()
                logger.info("agent.activity.start", activity=act_name)
                try:
                    result = await fn(*args, **kwargs)
                except Exception as exc:
                    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                    logger.exception(
                        "agent.activity.error",
                        activity=act_name,
                        duration_ms=elapsed_ms,
                        error=str(exc),
                    )
                    raise
                else:
                    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                    logger.info(
                        "agent.activity.end",
                        activity=act_name,
                        duration_ms=elapsed_ms,
                    )
                    return result
                finally:
                    _LOG_CONTEXT.reset(token)

            async_wrapper.agent_id = agent_id  # type: ignore[attr-defined]
            return cast(F, async_wrapper)

        @wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            token = _LOG_CONTEXT.set(
                {**_LOG_CONTEXT.get(), "agent_id": agent_id}
            )
            start = time.perf_counter()
            logger.info("agent.activity.start", activity=act_name)
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                logger.exception(
                    "agent.activity.error",
                    activity=act_name,
                    duration_ms=elapsed_ms,
                    error=str(exc),
                )
                raise
            else:
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                logger.info(
                    "agent.activity.end",
                    activity=act_name,
                    duration_ms=elapsed_ms,
                )
                return result
            finally:
                _LOG_CONTEXT.reset(token)

        sync_wrapper.agent_id = agent_id  # type: ignore[attr-defined]
        return cast(F, sync_wrapper)

    return decorator


# ── Workflow helper ──────────────────────────────────────────────────────────


def bind_workflow(workflow_id: str) -> None:
    """Convenience binder for workflow entry points."""
    bind_context(workflow_id=workflow_id)


__all__ = [
    "configure_logging",
    "get_logger",
    "bind_context",
    "clear_context",
    "get_context",
    "bind_workflow",
    "RequestLoggingMiddleware",
    "log_agent_activity",
]
