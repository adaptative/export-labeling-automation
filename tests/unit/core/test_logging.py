"""Tests for labelforge.core.logging (Sprint-15, TASK-039)."""
from __future__ import annotations

import asyncio
import json
import logging

import pytest

from labelforge.core import logging as llog
from labelforge.core.logging import (
    RequestLoggingMiddleware,
    _LOG_CONTEXT,
    bind_context,
    clear_context,
    configure_logging,
    get_context,
    get_logger,
    log_agent_activity,
)


@pytest.fixture(autouse=True)
def _fresh_logging():
    """Reset the structlog/stdlib handler state so ``capsys`` can see output.

    structlog's StreamHandler captures ``sys.stdout`` at handler-creation
    time. pytest's ``capsys`` swaps ``sys.stdout`` per test, so a handler
    installed once at module import writes to the *original* stdout and
    nothing lands in ``capsys.readouterr().out``. Resetting the module
    flag + clearing root handlers before each test forces
    :func:`configure_logging` to rebind to the current ``sys.stdout``.
    """
    _LOG_CONTEXT.set({})
    llog._CONFIGURED = False
    import structlog
    structlog.reset_defaults()
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    yield
    _LOG_CONTEXT.set({})


# ── Configuration ────────────────────────────────────────────────────────────


def test_configure_logging_is_idempotent():
    configure_logging("DEBUG")
    handlers_first = list(logging.getLogger().handlers)
    configure_logging("INFO")
    handlers_second = list(logging.getLogger().handlers)
    # No duplicate handlers on re-configuration.
    assert len(handlers_second) == len(handlers_first)


def test_configure_logging_reads_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    # Already configured from the fixture; call again to pick up env.
    configure_logging()
    # Root logger level tracks what we set.
    root = logging.getLogger()
    assert root.level == logging.WARNING


# ── Context helpers ──────────────────────────────────────────────────────────


class TestContext:
    def test_bind_merges(self):
        bind_context(tenant_id="t1", user_id="u1")
        bind_context(request_id="r1")
        assert dict(get_context()) == {
            "tenant_id": "t1",
            "user_id": "u1",
            "request_id": "r1",
        }

    def test_bind_none_drops_key(self):
        bind_context(tenant_id="t1")
        bind_context(tenant_id=None)
        assert "tenant_id" not in get_context()

    def test_clear_all(self):
        bind_context(tenant_id="t1", user_id="u1")
        clear_context()
        assert dict(get_context()) == {}

    def test_clear_specific_keys(self):
        bind_context(tenant_id="t1", user_id="u1", agent_id="a1")
        clear_context("user_id", "agent_id")
        assert dict(get_context()) == {"tenant_id": "t1"}

    def test_get_context_returns_copy(self):
        bind_context(tenant_id="t1")
        snapshot = get_context()
        bind_context(tenant_id="t2")
        # Snapshot is frozen at the time of get_context().
        assert dict(snapshot) == {"tenant_id": "t1"}


# ── JSON output ──────────────────────────────────────────────────────────────


class TestJSONOutput:
    def test_event_dict_contains_context_keys(self, capsys):
        configure_logging("INFO")
        bind_context(tenant_id="t1", user_id="u1", request_id="r1")
        logger = get_logger("test.json_output")
        logger.info("something.happened", extra_field="x")
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines() if ln.strip()]
        # Find the JSON line that corresponds to our event.
        our = next(ln for ln in lines if '"something.happened"' in ln)
        parsed = json.loads(our)
        assert parsed["event"] == "something.happened"
        assert parsed["tenant_id"] == "t1"
        assert parsed["user_id"] == "u1"
        assert parsed["request_id"] == "r1"
        assert parsed["extra_field"] == "x"
        assert "timestamp" in parsed
        assert parsed["level"] == "info"

    def test_each_log_line_is_valid_json(self, capsys):
        configure_logging("INFO")
        logger = get_logger("test.json_each")
        logger.info("a")
        logger.info("b")
        logger.warning("c")
        lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
        assert len(lines) >= 3
        for ln in lines:
            json.loads(ln)  # each line is valid JSON


# ── ASGI request middleware ──────────────────────────────────────────────────


async def _run_asgi(mw, scope, body=b"OK", status=200):
    """Tiny harness: capture sent messages, feed the middleware, return them."""
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    await mw(scope, receive, send)
    return sent


class TestRequestLoggingMiddleware:
    @pytest.mark.asyncio
    async def test_http_start_and_end_events(self, capsys):
        configure_logging("INFO")

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = RequestLoggingMiddleware(app)
        scope = {"type": "http", "method": "GET", "path": "/hello", "headers": []}
        sent = await _run_asgi(mw, scope)

        # x-request-id was echoed into response headers.
        start_msg = next(m for m in sent if m["type"] == "http.response.start")
        headers = dict(start_msg["headers"])
        assert b"x-request-id" in headers

        out = capsys.readouterr().out
        events = [json.loads(ln) for ln in out.splitlines() if ln.strip()]
        starts = [e for e in events if e["event"] == "request.start"]
        ends = [e for e in events if e["event"] == "request.end"]
        assert starts and ends
        assert starts[0]["path"] == "/hello"
        assert ends[0]["status"] == 204
        assert "duration_ms" in ends[0]
        # Both events share the same request_id.
        assert starts[0]["request_id"] == ends[0]["request_id"]

    @pytest.mark.asyncio
    async def test_incoming_x_request_id_is_preserved(self):
        captured: dict[str, str] = {}

        async def app(scope, receive, send):
            captured["rid"] = get_context().get("request_id", "")
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = RequestLoggingMiddleware(app)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": [(b"x-request-id", b"caller-supplied-id")],
        }
        await _run_asgi(mw, scope)
        assert captured["rid"] == "caller-supplied-id"

    @pytest.mark.asyncio
    async def test_request_error_logged_and_reraised(self, capsys):
        configure_logging("INFO")

        async def app(scope, receive, send):
            raise RuntimeError("boom")

        mw = RequestLoggingMiddleware(app)
        scope = {"type": "http", "method": "GET", "path": "/err", "headers": []}
        with pytest.raises(RuntimeError, match="boom"):
            await _run_asgi(mw, scope)

        events = [
            json.loads(ln)
            for ln in capsys.readouterr().out.splitlines()
            if ln.strip() and '"event":' in ln
        ]
        assert any(e["event"] == "request.error" for e in events)

    @pytest.mark.asyncio
    async def test_non_http_scope_passthrough(self):
        called: dict[str, bool] = {}

        async def app(scope, receive, send):
            called["hit"] = True

        mw = RequestLoggingMiddleware(app)
        # Lifespan scope must be handed through untouched.
        await mw({"type": "lifespan"}, None, None)
        assert called["hit"] is True

    @pytest.mark.asyncio
    async def test_request_id_cleared_after_request(self):
        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = RequestLoggingMiddleware(app)
        bind_context(tenant_id="outer")
        scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
        await _run_asgi(mw, scope)
        # After request completes, outer tenant_id remains but request_id is gone.
        ctx = get_context()
        assert ctx.get("tenant_id") == "outer"
        assert "request_id" not in ctx


# ── Agent activity decorator ─────────────────────────────────────────────────


class TestAgentActivityDecorator:
    @pytest.mark.asyncio
    async def test_async_decorator_binds_agent_id(self, capsys):
        configure_logging("INFO")

        observed: dict[str, str | None] = {}

        @log_agent_activity("agent.intake")
        async def run():
            observed["agent_id"] = get_context().get("agent_id")
            return "ok"

        assert run.agent_id == "agent.intake"
        out = await run()
        assert out == "ok"
        assert observed["agent_id"] == "agent.intake"
        # After the call agent_id is cleared.
        assert "agent_id" not in get_context()

        events = [
            json.loads(ln)
            for ln in capsys.readouterr().out.splitlines()
            if ln.strip() and '"event":' in ln
        ]
        assert any(e["event"] == "agent.activity.start" and e["agent_id"] == "agent.intake" for e in events)
        assert any(e["event"] == "agent.activity.end" and e["agent_id"] == "agent.intake" for e in events)

    def test_sync_decorator_works(self, capsys):
        configure_logging("INFO")

        @log_agent_activity("agent.sync", activity="do_thing")
        def work(x):
            return x * 2

        assert work(3) == 6
        events = [
            json.loads(ln)
            for ln in capsys.readouterr().out.splitlines()
            if ln.strip() and '"event":' in ln
        ]
        assert any(e.get("activity") == "do_thing" and e["event"] == "agent.activity.start" for e in events)
        assert any(e.get("activity") == "do_thing" and e["event"] == "agent.activity.end" for e in events)

    @pytest.mark.asyncio
    async def test_async_decorator_logs_and_reraises_on_error(self, capsys):
        configure_logging("INFO")

        @log_agent_activity("agent.err")
        async def bad():
            raise ValueError("nope")

        with pytest.raises(ValueError, match="nope"):
            await bad()
        events = [
            json.loads(ln)
            for ln in capsys.readouterr().out.splitlines()
            if ln.strip() and '"event":' in ln
        ]
        errs = [e for e in events if e["event"] == "agent.activity.error"]
        assert errs
        assert errs[0]["agent_id"] == "agent.err"
        assert "duration_ms" in errs[0]
        # agent_id cleared after failure.
        assert "agent_id" not in get_context()

    def test_sync_decorator_logs_and_reraises_on_error(self):
        @log_agent_activity("agent.sync_err")
        def boom():
            raise RuntimeError("bad")

        with pytest.raises(RuntimeError, match="bad"):
            boom()
        assert "agent_id" not in get_context()

    @pytest.mark.asyncio
    async def test_nested_agent_ids_restore_outer(self):
        observations: list[str | None] = []

        @log_agent_activity("outer")
        async def outer():
            observations.append(get_context().get("agent_id"))
            await inner()
            observations.append(get_context().get("agent_id"))

        @log_agent_activity("inner")
        async def inner():
            observations.append(get_context().get("agent_id"))

        await outer()
        # outer -> inner -> outer sequence.
        assert observations == ["outer", "inner", "outer"]


# ── Configurable level ───────────────────────────────────────────────────────


def test_debug_level_emits_debug_events(capsys):
    configure_logging("DEBUG")
    logger = get_logger("test.debug_level")
    logger.debug("quiet.stuff")
    out = capsys.readouterr().out
    assert '"event": "quiet.stuff"' in out or '"quiet.stuff"' in out


def test_warning_level_suppresses_info(capsys):
    configure_logging("WARNING")
    logger = get_logger("test.warn_level")
    logger.info("not.shown")
    logger.warning("shown")
    out = capsys.readouterr().out
    assert "not.shown" not in out
    assert "shown" in out
