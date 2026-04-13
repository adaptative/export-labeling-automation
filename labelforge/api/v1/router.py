"""Main API v1 router that includes all sub-routers."""
from __future__ import annotations

from fastapi import APIRouter

from labelforge.api.v1 import (
    admin,
    artifacts,
    audit_log,
    auth,
    documents,
    hitl,
    importers,
    items,
    notifications,
    orders,
    rules,
    settings,
    warning_labels,
)

api_router = APIRouter()

api_router.include_router(admin.router)
api_router.include_router(audit_log.router)
api_router.include_router(auth.router)
api_router.include_router(orders.router)
api_router.include_router(items.router)
api_router.include_router(documents.router)
api_router.include_router(hitl.router)
api_router.include_router(rules.router)
api_router.include_router(importers.router)
api_router.include_router(artifacts.router)
api_router.include_router(notifications.router)
api_router.include_router(settings.router)
api_router.include_router(warning_labels.router)


@api_router.get("/ping")
async def ping() -> dict[str, str]:
    """Minimal readiness probe for the API v1 prefix."""
    return {"ping": "pong"}
