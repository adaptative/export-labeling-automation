"""Row-Level Security tenant middleware."""
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_current_tenant: ContextVar[Optional[str]] = ContextVar("current_tenant", default=None)


def get_current_tenant() -> Optional[str]:
    return _current_tenant.get()


def set_current_tenant(tenant_id: Optional[str]) -> None:
    _current_tenant.set(tenant_id)


class TenantMiddleware:
    """ASGI middleware that extracts tenant_id from JWT and sets it for RLS."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            tenant_id = self._extract_tenant(scope)
            set_current_tenant(tenant_id)
        await self.app(scope, receive, send)

    def _extract_tenant(self, scope) -> Optional[str]:
        headers = dict(scope.get("headers", []))
        token_header = headers.get(b"authorization", b"").decode()
        if not token_header.startswith("Bearer "):
            return None
        # In production: decode JWT, extract tenant_id
        # Stub: return None if no valid token
        return None


async def set_rls_tenant(conn, tenant_id: Optional[str]) -> None:
    """Set PostgreSQL session variable for RLS. Fail-closed: no tenant = no access."""
    if tenant_id is None:
        await conn.execute("SET LOCAL app.tenant_id = ''")
    else:
        await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_id}'")
