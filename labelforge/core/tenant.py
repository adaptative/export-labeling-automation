"""Row-Level Security tenant middleware and helpers.

The TenantMiddleware extracts tenant_id from the request (JWT or header)
and stores it in a ContextVar. The ``set_rls_tenant`` function sets the
PostgreSQL session variable ``app.tenant_id`` for RLS enforcement.

Fail-closed: if no tenant_id is set, an empty string is used, which
won't match any UUID tenant_id, so zero rows are returned.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_current_tenant: ContextVar[Optional[str]] = ContextVar("current_tenant", default=None)


def get_current_tenant() -> Optional[str]:
    return _current_tenant.get()


def set_current_tenant(tenant_id: Optional[str]) -> None:
    _current_tenant.set(tenant_id)


class TenantMiddleware:
    """ASGI middleware that extracts tenant_id from JWT/header and sets ContextVar."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            tenant_id = self._extract_tenant(scope)
            set_current_tenant(tenant_id)
        await self.app(scope, receive, send)

    def _extract_tenant(self, scope) -> Optional[str]:
        headers = dict(scope.get("headers", []))
        # Check X-Tenant-ID header first (for testing / service-to-service)
        tenant_header = headers.get(b"x-tenant-id", b"").decode()
        if tenant_header:
            return tenant_header
        # Then check Authorization Bearer token
        token_header = headers.get(b"authorization", b"").decode()
        if not token_header.startswith("Bearer "):
            return None
        # In production: decode JWT, extract tenant_id claim
        # Stub: return None if no valid token
        return None


async def set_rls_tenant(conn, tenant_id: Optional[str]) -> None:
    """Set PostgreSQL session variable for RLS.

    Fail-closed: no tenant = empty string which matches no UUID,
    so RLS policies return zero rows.
    """
    safe_id = ""
    if tenant_id is not None:
        # Basic validation: only allow UUID-like strings
        clean = tenant_id.replace("-", "")
        if len(clean) == 32 and all(c in "0123456789abcdef" for c in clean.lower()):
            safe_id = tenant_id
    await conn.execute(f"SET LOCAL app.tenant_id = '{safe_id}'")
