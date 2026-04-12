"""Tests for labelforge.core.auth — TASK-004 (Auth + RBAC)."""
import base64
import json
import time

import pytest
from unittest.mock import AsyncMock

from labelforge.core.auth import (
    AuthError,
    Capability,
    Role,
    ROLE_CAPABILITIES,
    TokenPayload,
    check_revocation,
    decode_token,
    require_capability,
)


def _make_jwt_payload(payload: dict) -> str:
    """Build a fake JWT (header.payload.signature) with given payload dict."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    sig = base64.urlsafe_b64encode(b"fakesig").rstrip(b"=")
    return f"{header.decode()}.{body.decode()}.{sig.decode()}"


def _valid_payload(**overrides) -> dict:
    defaults = {
        "sub": "user-1",
        "tenant_id": "tenant-1",
        "role": "ADMIN",
        "capabilities": [],
        "exp": time.time() + 3600,
    }
    defaults.update(overrides)
    return defaults


class TestCapabilities:
    def test_seventeen_capabilities_exist(self):
        assert len(Capability) == 17

    def test_all_capabilities_are_strings(self):
        for cap in Capability:
            assert isinstance(cap.value, str)


class TestRoles:
    def test_four_roles_exist(self):
        assert len(Role) == 4

    def test_role_names(self):
        assert set(Role) == {Role.ADMIN, Role.COMPLIANCE, Role.OPS, Role.EXTERNAL}


class TestRoleCapabilities:
    def test_admin_has_all_capabilities(self):
        assert ROLE_CAPABILITIES[Role.ADMIN] == set(Capability)

    def test_external_only_has_portal_caps(self):
        external_caps = ROLE_CAPABILITIES[Role.EXTERNAL]
        assert external_caps == {
            Capability.ORDER_VIEW,
            Capability.PORTAL_APPROVE,
            Capability.PORTAL_DOWNLOAD,
        }

    def test_ops_cannot_promote_rules(self):
        assert Capability.RULE_PROMOTE not in ROLE_CAPABILITIES[Role.OPS]

    def test_compliance_can_promote_rules(self):
        assert Capability.RULE_PROMOTE in ROLE_CAPABILITIES[Role.COMPLIANCE]

    def test_ops_capabilities(self):
        ops_caps = ROLE_CAPABILITIES[Role.OPS]
        assert Capability.ORDER_CREATE in ops_caps
        assert Capability.ORDER_VIEW in ops_caps
        assert Capability.ORDER_REPROCESS in ops_caps
        assert Capability.ITEM_REPRODUCE in ops_caps
        assert Capability.RULE_VIEW in ops_caps

    def test_compliance_capabilities(self):
        comp_caps = ROLE_CAPABILITIES[Role.COMPLIANCE]
        assert Capability.AUDIT_VIEW in comp_caps
        assert Capability.WARNING_LABEL_EDIT in comp_caps
        assert Capability.IMPORTER_PROFILE_EDIT in comp_caps


class TestRequireCapability:
    def test_raises_403_when_missing(self):
        token = TokenPayload(
            user_id="u1",
            tenant_id="t1",
            role=Role.EXTERNAL,
            capabilities=set(),
            exp=time.time() + 3600,
        )
        with pytest.raises(AuthError) as exc_info:
            require_capability(token, Capability.RULE_PROMOTE)
        assert exc_info.value.status_code == 403

    def test_passes_for_role_capability(self):
        token = TokenPayload(
            user_id="u1",
            tenant_id="t1",
            role=Role.ADMIN,
            capabilities=set(),
            exp=time.time() + 3600,
        )
        # Should not raise
        require_capability(token, Capability.RULE_PROMOTE)

    def test_passes_for_explicit_capability(self):
        token = TokenPayload(
            user_id="u1",
            tenant_id="t1",
            role=Role.EXTERNAL,
            capabilities={Capability.RULE_PROMOTE},
            exp=time.time() + 3600,
        )
        # Extra capability granted explicitly
        require_capability(token, Capability.RULE_PROMOTE)


class TestDecodeToken:
    def test_expired_token_raises_401(self):
        payload = _valid_payload(exp=time.time() - 100)
        token = _make_jwt_payload(payload)
        with pytest.raises(AuthError) as exc_info:
            decode_token(token, "secret")
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_invalid_format_raises_401(self):
        with pytest.raises(AuthError) as exc_info:
            decode_token("not-a-jwt", "secret")
        assert exc_info.value.status_code == 401

    def test_valid_token_decodes(self):
        payload = _valid_payload(
            sub="user-42",
            tenant_id="tenant-99",
            role="OPS",
            capabilities=["order.create"],
        )
        token = _make_jwt_payload(payload)
        result = decode_token(token, "secret")
        assert result.user_id == "user-42"
        assert result.tenant_id == "tenant-99"
        assert result.role == Role.OPS
        assert Capability.ORDER_CREATE in result.capabilities

    def test_missing_required_field_raises_401(self):
        payload = {"exp": time.time() + 3600}  # missing sub, tenant_id, role
        token = _make_jwt_payload(payload)
        with pytest.raises(AuthError) as exc_info:
            decode_token(token, "secret")
        assert exc_info.value.status_code == 401

    def test_portal_order_id_scoping_for_external(self):
        payload = _valid_payload(
            role="EXTERNAL",
            portal_order_id="order-777",
        )
        token = _make_jwt_payload(payload)
        result = decode_token(token, "secret")
        assert result.portal_order_id == "order-777"
        assert result.role == Role.EXTERNAL


class TestCheckRevocation:
    @pytest.mark.asyncio
    async def test_returns_true_for_revoked_token(self):
        redis = AsyncMock()
        redis.exists.return_value = True
        result = await check_revocation("some.jwt.token", redis)
        assert result is True
        redis.exists.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_for_valid_token(self):
        redis = AsyncMock()
        redis.exists.return_value = False
        result = await check_revocation("valid.jwt.token", redis)
        assert result is False
