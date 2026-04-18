"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from labelforge.config import settings
from labelforge.api.v1.router import api_router
from labelforge.api.v1.errors import register_error_handlers
from labelforge.core.logging import (
    RequestLoggingMiddleware,
    configure_logging,
    get_logger,
)
from labelforge.core.metrics import PrometheusMiddleware, render_metrics
from labelforge.core.tracing import (
    configure_tracing,
    instrument_fastapi,
    instrument_httpx,
    instrument_sqlalchemy,
)

# Configure structured JSON logging + OTel tracing before any other
# module emits logs / spans.
configure_logging()
configure_tracing(service_name="labelforge-api")
_log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables, seed data, and wire Redis cache on startup."""
    from labelforge.db.session import create_all_tables, engine as db_engine
    from labelforge.db.seed import seed_if_empty
    await create_all_tables()
    await seed_if_empty()

    # Attach DB spans to the live engine (safe to call multiple times).
    try:
        instrument_sqlalchemy(db_engine)
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("tracing.sqlalchemy_instrument_skipped", error=str(exc))

    # Install the HITL auto-advance hook so chat handlers that signal
    # ``resolved: true`` can push the order's pipeline forward without
    # an operator click. Also pre-imports the chat-handler registry so
    # the dispatcher can find a handler on the very first human reply.
    try:
        from labelforge.services.hitl.auto_advance import install as install_auto_advance
        import labelforge.agents.chat_handlers  # noqa: F401 — registration side effect
        install_auto_advance()
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("hitl.auto_advance_install_skipped", error=str(exc))

    # Wire Redis-backed LLM completion cache + HiTL MessageRouter. The
    # router falls back to in-memory when Redis is unavailable so tests
    # and single-worker dev work without extra setup.
    redis_client = None
    hitl_router = None
    if settings.redis_url and settings.app_env != "test":
        try:
            import redis.asyncio as aioredis
            from labelforge.core.llm import RedisCompletionCache, set_default_cache
            from labelforge.services.hitl import (
                RedisMessageRouter,
                set_message_router,
            )
            redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
            await redis_client.ping()
            set_default_cache(RedisCompletionCache(redis_client))
            hitl_router = RedisMessageRouter(redis_client)
            set_message_router(hitl_router)
            _log.info(
                "redis.connected",
                component="llm_cache+hitl_router",
                url=settings.redis_url,
            )
        except Exception as exc:
            _log.warning(
                "redis.unavailable",
                component="llm_cache+hitl_router",
                error=str(exc),
            )

    yield

    if hitl_router:
        from labelforge.services.hitl import set_message_router
        try:
            await hitl_router.aclose()
        finally:
            set_message_router(None)
    if redis_client:
        await redis_client.aclose()


app = FastAPI(
    title="Labelforge API",
    description="AI-driven export labeling automation",
    version="0.1.0",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

# Structured request/response logging. Installed before CORS so every
# request gets a request_id (logged even on preflight).
app.add_middleware(RequestLoggingMiddleware)

# Prometheus request histogram. Comes after RequestLoggingMiddleware in
# the code so it wraps innermost (ASGI middleware runs in reverse
# registration order), meaning request_id is already bound when we
# observe the histogram.
app.add_middleware(PrometheusMiddleware)

# Auto-instrument FastAPI + outbound httpx for OTel spans. SQLAlchemy
# is instrumented inside the lifespan once the engine exists.
instrument_fastapi(app)
instrument_httpx()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register standardized error handlers
register_error_handlers(app)

# Mount all API routes under /api/v1
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus scrape endpoint."""
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)
