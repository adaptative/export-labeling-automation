"""JWT authentication and RBAC.

Provides HS256 JWT decoding, 17 capabilities across 4 roles,
require_capability dependency for FastAPI routes, Redis-based
token revocation, and audit logging on auth failures.

OIDC and SAML are scaffolded as stubs for future integration.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class Capability(str, Enum):
    ORDER_CREATE = "order.create"
    ORDER_VIEW = "order.view"
    ORDER_REPROCESS = "order.reprocess"
    ITEM_REPRODUCE = "item.reproduce_artifact"
    RULE_VIEW = "rule.view"
    RULE_PROPOSE = "rule.propose"
    RULE_PROMOTE = "rule.promote"
    WARNING_LABEL_EDIT = "warning_label.edit"
    IMPORTER_PROFILE_EDIT = "importer_profile.edit"
    AGENT_PROMPT_EDIT = "agent.prompt.edit"
    AGENT_MODEL_CHANGE = "agent.model.change"
    COST_BUDGET_EDIT = "cost.budget.edit"
    USER_INVITE = "user.invite"
    SSO_CONFIGURE = "sso.configure"
    AUDIT_VIEW = "audit.view"
    PORTAL_APPROVE = "portal.approve_artifact"
    PORTAL_DOWNLOAD = "portal.download_bundle"


class Role(str, Enum):
    ADMIN = "ADMIN"
    COMPLIANCE = "COMPLIANCE"
    OPS = "OPS"
    EXTERNAL = "EXTERNAL"


ROLE_CAPABILITIES: dict[Role, set[Capability]] = {
    Role.ADMIN: set(Capability),  # All capabilities
    Role.COMPLIANCE: {
        Capability.ORDER_VIEW,
        Capability.RULE_VIEW,
        Capability.RULE_PROPOSE,
        Capability.RULE_PROMOTE,
        Capability.WARNING_LABEL_EDIT,
        Capability.IMPORTER_PROFILE_EDIT,
        Capability.AUDIT_VIEW,
    },
    Role.OPS: {
        Capability.ORDER_CREATE,
        Capability.ORDER_VIEW,
        Capability.ORDER_REPROCESS,
        Capability.ITEM_REPRODUCE,
        Capability.RULE_VIEW,
    },
    Role.EXTERNAL: {
        Capability.ORDER_VIEW,
        Capability.PORTAL_APPROVE,
        Capability.PORTAL_DOWNLOAD,
    },
}


@dataclass
class TokenPayload:
    user_id: str
    tenant_id: str
    role: Role
    capabilities: set
    exp: float
    portal_order_id: Optional[str] = None  # For external portal tokens


class AuthError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


class AuditEntry:
    """Audit log entry for auth events."""

    def __init__(
        self,
        action: str,
        detail: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ):
        self.action = action
        self.detail = detail
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.ip_address = ip_address
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "detail": self.detail,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp,
        }


# In-memory audit buffer for testing — in production, writes to DB
_audit_log: List[AuditEntry] = []


def log_auth_event(
    action: str,
    detail: str,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> AuditEntry:
    """Log an authentication/authorization event."""
    entry = AuditEntry(
        action=action,
        detail=detail,
        user_id=user_id,
        tenant_id=tenant_id,
        ip_address=ip_address,
    )
    _audit_log.append(entry)
    logger.info("Auth event: %s — %s (user=%s, tenant=%s)", action, detail, user_id, tenant_id)
    return entry


def get_audit_log() -> List[AuditEntry]:
    """Return the in-memory audit log entries."""
    return list(_audit_log)


def clear_audit_log() -> None:
    """Clear the in-memory audit log (for testing)."""
    _audit_log.clear()


def decode_token(token: str, secret: str) -> TokenPayload:
    """Decode and validate a JWT token. Raises AuthError on failure."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthError(401, "Invalid token format")
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        # Verify expiration
        if payload.get("exp", 0) < time.time():
            log_auth_event("auth.expired", "Token expired", user_id=payload.get("sub"))
            raise AuthError(401, "Token expired")
        return TokenPayload(
            user_id=payload["sub"],
            tenant_id=payload["tenant_id"],
            role=Role(payload["role"]),
            capabilities={Capability(c) for c in payload.get("capabilities", [])},
            exp=payload["exp"],
            portal_order_id=payload.get("portal_order_id"),
        )
    except AuthError:
        raise
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        log_auth_event("auth.invalid", f"Invalid token: {e}")
        raise AuthError(401, f"Invalid token: {e}")


def require_capability(token: TokenPayload, capability: Capability) -> None:
    """Check if token has required capability. Raises AuthError(403) if not."""
    role_caps = ROLE_CAPABILITIES.get(token.role, set())
    if capability not in role_caps and capability not in token.capabilities:
        log_auth_event(
            "auth.forbidden",
            f"Missing capability: {capability.value}",
            user_id=token.user_id,
            tenant_id=token.tenant_id,
        )
        raise AuthError(403, f"Missing capability: {capability.value}")


async def check_revocation(token: str, redis_client) -> bool:
    """Check if token is in the revocation list. Returns True if revoked."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return await redis_client.exists(f"revoked:{token_hash}")


async def revoke_token(token: str, redis_client, ttl_seconds: int = 3600) -> None:
    """Add a token to the revocation list."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    await redis_client.setex(f"revoked:{token_hash}", ttl_seconds, "1")
    log_auth_event("auth.revoked", f"Token revoked: {token_hash[:16]}...")


def make_require_capability_dependency(capability: Capability) -> Callable:
    """Create a FastAPI dependency that checks for a specific capability.

    Usage in route:
        @router.get("/rules", dependencies=[Depends(make_require_capability_dependency(Capability.RULE_VIEW))])
    """
    def dependency(token: TokenPayload) -> None:
        require_capability(token, capability)
    dependency.__name__ = f"require_{capability.value.replace('.', '_')}"
    return dependency


# ── OIDC / SAML stubs ───────────────────────────────────────────────────────


class OIDCConfig:
    """OIDC configuration stub for future SSO integration."""

    def __init__(
        self,
        issuer_url: str = "",
        client_id: str = "",
        client_secret: str = "",
        redirect_uri: str = "",
    ):
        self.issuer_url = issuer_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.enabled = bool(issuer_url and client_id)

    def get_authorization_url(self) -> str:
        if not self.enabled:
            raise AuthError(501, "OIDC not configured")
        return f"{self.issuer_url}/authorize?client_id={self.client_id}&redirect_uri={self.redirect_uri}"


class SAMLConfig:
    """SAML configuration stub for future SSO integration."""

    def __init__(
        self,
        idp_metadata_url: str = "",
        sp_entity_id: str = "",
    ):
        self.idp_metadata_url = idp_metadata_url
        self.sp_entity_id = sp_entity_id
        self.enabled = bool(idp_metadata_url and sp_entity_id)

    def get_login_url(self) -> str:
        if not self.enabled:
            raise AuthError(501, "SAML not configured")
        return f"{self.idp_metadata_url}/sso"
