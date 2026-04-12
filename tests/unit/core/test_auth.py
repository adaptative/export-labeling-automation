"""Tests for labelforge.core.auth — TASK-004 (Auth + RBAC)."""
import base64
import json
import time

import pytest
from unittest.mock import AsyncMock

from labelforge.core.auth import (
    AuditEntry,
    AuthError,
    Capability,
    OIDCConfig,
    Role,
    ROLE_CAPABILITIES,
    SAMLConfig,
    TokenPayload,
    check_revocation,
    clear_audit_log,
    decode_token,
    get_audit_log,
    log_auth_event,
    make_require_capability_dependency,
    require_capability,
    revoke_token,
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
        require_capability(token, Capability.RULE_PROMOTE)

    def test_passes_for_explicit_capability(self):
        token = TokenPayload(
            user_id="u1",
            tenant_id="t1",
            role=Role.EXTERNAL,
            capabilities={Capability.RULE_PROMOTE},
            exp=time.time() + 3600,
        )
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
        payload = {"exp": time.time() + 3600}
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


class TestRevokeToken:
    @pytest.mark.asyncio
    async def test_revoke_token_calls_redis_setex(self):
        redis = AsyncMock()
        await revoke_token("some.jwt.token", redis, ttl_seconds=7200)
        redis.setex.assert_awaited_once()
        args = redis.setex.await_args
        assert args[0][0].startswith("revoked:")
        assert args[0][1] == 7200


class TestAuditLogging:
    def setup_method(self):
        clear_audit_log()

    def test_log_auth_event_creates_entry(self):
        entry = log_auth_event("auth.failed", "bad token", user_id="u1")
        assert entry.action == "auth.failed"
        assert entry.detail == "bad token"
        assert entry.user_id == "u1"

    def test_audit_log_accumulates(self):
        log_auth_event("auth.failed", "attempt 1")
        log_auth_event("auth.failed", "attempt 2")
        log = get_audit_log()
        assert len(log) == 2

    def test_clear_audit_log(self):
        log_auth_event("auth.failed", "test")
        clear_audit_log()
        assert len(get_audit_log()) == 0

    def test_audit_entry_to_dict(self):
        entry = AuditEntry(
            action="auth.failed",
            detail="bad token",
            user_id="u1",
            tenant_id="t1",
            ip_address="127.0.0.1",
        )
        d = entry.to_dict()
        assert d["action"] == "auth.failed"
        assert d["user_id"] == "u1"
        assert "timestamp" in d

    def test_expired_token_logs_audit(self):
        payload = _valid_payload(exp=time.time() - 100)
        token = _make_jwt_payload(payload)
        with pytest.raises(AuthError):
            decode_token(token, "secret")
        log = get_audit_log()
        assert any(e.action == "auth.expired" for e in log)

    def test_invalid_token_logs_audit(self):
        payload = {"exp": time.time() + 3600}
        token = _make_jwt_payload(payload)
        with pytest.raises(AuthError):
            decode_token(token, "secret")
        log = get_audit_log()
        assert any(e.action == "auth.invalid" for e in log)

    def test_forbidden_logs_audit(self):
        token = TokenPayload(
            user_id="u1", tenant_id="t1", role=Role.EXTERNAL,
            capabilities=set(), exp=time.time() + 3600,
        )
        with pytest.raises(AuthError):
            require_capability(token, Capability.RULE_PROMOTE)
        log = get_audit_log()
        assert any(e.action == "auth.forbidden" for e in log)


class TestMakeRequireCapabilityDependency:
    def test_creates_callable(self):
        dep = make_require_capability_dependency(Capability.ORDER_VIEW)
        assert callable(dep)

    def test_passes_with_valid_capability(self):
        dep = make_require_capability_dependency(Capability.ORDER_VIEW)
        token = TokenPayload(
            user_id="u1", tenant_id="t1", role=Role.ADMIN,
            capabilities=set(), exp=time.time() + 3600,
        )
        dep(token)  # should not raise

    def test_raises_with_missing_capability(self):
        dep = make_require_capability_dependency(Capability.SSO_CONFIGURE)
        token = TokenPayload(
            user_id="u1", tenant_id="t1", role=Role.EXTERNAL,
            capabilities=set(), exp=time.time() + 3600,
        )
        with pytest.raises(AuthError) as exc_info:
            dep(token)
        assert exc_info.value.status_code == 403


class TestOIDCConfig:
    def test_not_enabled_by_default(self):
        oidc = OIDCConfig()
        assert not oidc.enabled

    def test_enabled_when_configured(self):
        oidc = OIDCConfig(issuer_url="https://idp.example.com", client_id="abc")
        assert oidc.enabled

    def test_get_authorization_url_raises_when_not_configured(self):
        oidc = OIDCConfig()
        with pytest.raises(AuthError) as exc_info:
            oidc.get_authorization_url()
        assert exc_info.value.status_code == 501

    def test_get_authorization_url_when_configured(self):
        oidc = OIDCConfig(
            issuer_url="https://idp.example.com",
            client_id="abc",
            redirect_uri="https://app.example.com/callback",
        )
        url = oidc.get_authorization_url()
        assert "authorize" in url
        assert "abc" in url


class TestSAMLConfig:
    def test_not_enabled_by_default(self):
        saml = SAMLConfig()
        assert not saml.enabled

    def test_enabled_when_configured(self):
        saml = SAMLConfig(
            idp_metadata_url="https://idp.example.com/metadata",
            sp_entity_id="labelforge",
        )
        assert saml.enabled

    def test_get_login_url_raises_when_not_configured(self):
        saml = SAMLConfig()
        with pytest.raises(AuthError) as exc_info:
            saml.get_login_url()
        assert exc_info.value.status_code == 501
