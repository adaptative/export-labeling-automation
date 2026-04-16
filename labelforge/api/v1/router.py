"""Main API v1 router that includes all sub-routers."""
from __future__ import annotations

from fastapi import APIRouter

from labelforge.api.v1 import (
    admin,
    artifacts,
    audit_log,
    auth,
    budgets,
    dashboard,
    documents,
    hitl,
    importers,
    item_artifacts,
    line_drawing,
    items,
    notifications,
    orders,
    portal,
    rules,
    settings,
    warning_labels,
)

api_router = APIRouter()

api_router.include_router(admin.router)
api_router.include_router(audit_log.router)
api_router.include_router(auth.router)
api_router.include_router(budgets.router)
api_router.include_router(dashboard.router)
api_router.include_router(orders.router)
api_router.include_router(items.router)
api_router.include_router(item_artifacts.router)
api_router.include_router(documents.router)
api_router.include_router(portal.router)
api_router.include_router(hitl.router)
api_router.include_router(line_drawing.router)
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
