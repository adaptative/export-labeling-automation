"""Main API v1 router — sub-routers are added by feature tasks."""
from __future__ import annotations

from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/ping")
async def ping() -> dict[str, str]:
    """Minimal readiness probe for the API v1 prefix."""
    return {"ping": "pong"}
