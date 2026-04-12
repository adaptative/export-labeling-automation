"""Tests for labelforge.core.tenant — TASK-003 (RLS + TenantMiddleware)."""
import pytest
from unittest.mock import AsyncMock

from labelforge.core.tenant import (
    get_current_tenant,
    set_current_tenant,
    set_rls_tenant,
    TenantMiddleware,
)

VALID_TENANT_UUID = "12345678-1234-1234-1234-1234567890ab"
VALID_TENANT_UUID_2 = "aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb"


class TestCurrentTenant:
    def test_default_is_none(self):
        set_current_tenant(None)
        assert get_current_tenant() is None

    def test_set_and_get(self):
        set_current_tenant(VALID_TENANT_UUID)
        assert get_current_tenant() == VALID_TENANT_UUID
        set_current_tenant(None)  # cleanup

    def test_set_overwrites_previous(self):
        set_current_tenant(VALID_TENANT_UUID)
        set_current_tenant(VALID_TENANT_UUID_2)
        assert get_current_tenant() == VALID_TENANT_UUID_2
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
    async def test_extract_tenant_returns_none_for_stub_jwt(self):
        middleware = TenantMiddleware(AsyncMock())
        scope = {
            "type": "http",
            "headers": [(b"authorization", b"Bearer some.jwt.token")],
        }
        result = middleware._extract_tenant(scope)
        # Stub returns None until JWT decoding is implemented
        assert result is None

    @pytest.mark.asyncio
    async def test_extract_tenant_from_x_tenant_id_header(self):
        middleware = TenantMiddleware(AsyncMock())
        scope = {
            "type": "http",
            "headers": [(b"x-tenant-id", VALID_TENANT_UUID.encode())],
        }
        result = middleware._extract_tenant(scope)
        assert result == VALID_TENANT_UUID

    @pytest.mark.asyncio
    async def test_x_tenant_id_header_sets_context_var(self):
        app = AsyncMock()
        middleware = TenantMiddleware(app)
        scope = {
            "type": "http",
            "headers": [(b"x-tenant-id", VALID_TENANT_UUID.encode())],
        }
        await middleware(scope, AsyncMock(), AsyncMock())
        assert get_current_tenant() == VALID_TENANT_UUID
        set_current_tenant(None)  # cleanup


class TestSetRlsTenant:
    @pytest.mark.asyncio
    async def test_fail_closed_none_tenant_sets_empty_string(self):
        conn = AsyncMock()
        await set_rls_tenant(conn, None)
        conn.execute.assert_awaited_once_with("SET LOCAL app.tenant_id = ''")

    @pytest.mark.asyncio
    async def test_sets_valid_uuid_tenant(self):
        conn = AsyncMock()
        await set_rls_tenant(conn, VALID_TENANT_UUID)
        conn.execute.assert_awaited_once_with(
            f"SET LOCAL app.tenant_id = '{VALID_TENANT_UUID}'"
        )

    @pytest.mark.asyncio
    async def test_different_tenants_produce_different_sql(self):
        conn = AsyncMock()
        await set_rls_tenant(conn, VALID_TENANT_UUID)
        await set_rls_tenant(conn, VALID_TENANT_UUID_2)
        calls = [c.args[0] for c in conn.execute.await_args_list]
        assert calls[0] == f"SET LOCAL app.tenant_id = '{VALID_TENANT_UUID}'"
        assert calls[1] == f"SET LOCAL app.tenant_id = '{VALID_TENANT_UUID_2}'"

    @pytest.mark.asyncio
    async def test_rejects_non_uuid_tenant_id(self):
        conn = AsyncMock()
        await set_rls_tenant(conn, "malicious'; DROP TABLE users; --")
        conn.execute.assert_awaited_once_with("SET LOCAL app.tenant_id = ''")

    @pytest.mark.asyncio
    async def test_rejects_empty_string_tenant_id(self):
        conn = AsyncMock()
        await set_rls_tenant(conn, "")
        conn.execute.assert_awaited_once_with("SET LOCAL app.tenant_id = ''")
