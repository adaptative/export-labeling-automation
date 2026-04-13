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
    """Create tables and seed data on startup."""
    from labelforge.db.session import create_all_tables
    from labelforge.db.seed import seed_if_empty
    await create_all_tables()
    await seed_if_empty()
    yield


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
