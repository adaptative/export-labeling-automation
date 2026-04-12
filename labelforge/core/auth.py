"""JWT authentication and RBAC."""
from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Set


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
    capabilities: set[Capability]
    exp: float
    portal_order_id: Optional[str] = None  # For external portal tokens


class AuthError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


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
        raise AuthError(401, f"Invalid token: {e}")


def require_capability(token: TokenPayload, capability: Capability) -> None:
    """Check if token has required capability. Raises AuthError(403) if not."""
    role_caps = ROLE_CAPABILITIES.get(token.role, set())
    if capability not in role_caps and capability not in token.capabilities:
        raise AuthError(403, f"Missing capability: {capability.value}")


async def check_revocation(token: str, redis_client) -> bool:
    """Check if token is in the revocation list. Returns True if revoked."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return await redis_client.exists(f"revoked:{token_hash}")
