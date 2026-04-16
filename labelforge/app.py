"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from labelforge.config import settings
from labelforge.api.v1.router import api_router
from labelforge.api.v1.errors import register_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables, seed data, and wire Redis cache on startup."""
    from labelforge.db.session import create_all_tables
    from labelforge.db.seed import seed_if_empty
    await create_all_tables()
    await seed_if_empty()

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
            import logging
            logging.getLogger(__name__).info(
                "Redis connected (LLM cache + HiTL router): %s", settings.redis_url,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Redis unavailable, using in-memory (LLM cache + HiTL router): %s", exc,
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
