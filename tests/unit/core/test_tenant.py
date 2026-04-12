"""Tests for labelforge.core.tenant — TASK-003 (RLS + TenantMiddleware)."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from labelforge.core.tenant import (
    get_current_tenant,
    set_current_tenant,
    set_rls_tenant,
    TenantMiddleware,
)


class TestCurrentTenant:
    def test_default_is_none(self):
        set_current_tenant(None)
        assert get_current_tenant() is None

    def test_set_and_get(self):
        set_current_tenant("tenant-abc")
        assert get_current_tenant() == "tenant-abc"
        set_current_tenant(None)  # cleanup

    def test_set_overwrites_previous(self):
        set_current_tenant("t1")
        set_current_tenant("t2")
        assert get_current_tenant() == "t2"
        set_current_tenant(None)


class TestTenantMiddleware:
    @pytest.mark.asyncio
    async def test_sets_tenant_none_without_auth_header(self):
        app = AsyncMock()
        middleware = TenantMiddleware(app)
        scope = {"type": "http", "headers": []}
        await middleware(scope, AsyncMock(), AsyncMock())
        assert get_current_tenant() is None
        app.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sets_tenant_none_with_invalid_auth(self):
        app = AsyncMock()
        middleware = TenantMiddleware(app)
        scope = {
            "type": "http",
            "headers": [(b"authorization", b"Basic abc123")],
        }
        await middleware(scope, AsyncMock(), AsyncMock())
        assert get_current_tenant() is None

    @pytest.mark.asyncio
    async def test_passes_through_non_http_scopes(self):
        app = AsyncMock()
        middleware = TenantMiddleware(app)
        scope = {"type": "lifespan"}
        await middleware(scope, AsyncMock(), AsyncMock())
        app.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_extract_tenant_returns_none_for_stub(self):
        middleware = TenantMiddleware(AsyncMock())
        scope = {
            "type": "http",
            "headers": [(b"authorization", b"Bearer some.jwt.token")],
        }
        result = middleware._extract_tenant(scope)
        # Stub always returns None until JWT decoding is implemented
        assert result is None


class TestSetRlsTenant:
    @pytest.mark.asyncio
    async def test_fail_closed_none_tenant_sets_empty_string(self):
        conn = AsyncMock()
        await set_rls_tenant(conn, None)
        conn.execute.assert_awaited_once_with("SET LOCAL app.tenant_id = ''")

    @pytest.mark.asyncio
    async def test_sets_tenant_id_in_sql(self):
        conn = AsyncMock()
        await set_rls_tenant(conn, "tenant-xyz")
        conn.execute.assert_awaited_once_with(
            "SET LOCAL app.tenant_id = 'tenant-xyz'"
        )

    @pytest.mark.asyncio
    async def test_different_tenants_produce_different_sql(self):
        conn = AsyncMock()
        await set_rls_tenant(conn, "t1")
        await set_rls_tenant(conn, "t2")
        calls = [c.args[0] for c in conn.execute.await_args_list]
        assert calls[0] == "SET LOCAL app.tenant_id = 't1'"
        assert calls[1] == "SET LOCAL app.tenant_id = 't2'"
