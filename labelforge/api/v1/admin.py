"""Admin API routes — user management and SSO configuration."""
from __future__ import annotations

import hashlib
import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from labelforge.core.auth import Role, log_auth_event

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Request / Response models ────────────────────────────────────────────────


class UserResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: str
    status: str
    last_active: Optional[str] = None
    created_at: str


class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int


class InviteUserRequest(BaseModel):
    email: str
    display_name: str
    role: str = Field(default="OPS", description="One of ADMIN, OPS, COMPLIANCE, EXTERNAL")


class InviteUserResponse(BaseModel):
    user_id: str
    email: str
    message: str


class UpdateRoleRequest(BaseModel):
    role: str


class SSOConfigResponse(BaseModel):
    oidc_google_enabled: bool
    oidc_google_client_id: Optional[str] = None
    saml_microsoft_enabled: bool
    saml_microsoft_entity_id: Optional[str] = None


class UpdateSSOConfigRequest(BaseModel):
    oidc_google_enabled: Optional[bool] = None
    oidc_google_client_id: Optional[str] = None
    oidc_google_client_secret: Optional[str] = None
    saml_microsoft_enabled: Optional[bool] = None
    saml_microsoft_entity_id: Optional[str] = None
    saml_microsoft_metadata_url: Optional[str] = None


# ── Stub data ───────────────────────────────────────────────────────────────

_STUB_USERS: List[dict] = [
    {
        "user_id": "usr-admin-001",
        "email": "admin@nakodacraft.com",
        "display_name": "Admin User",
        "role": "ADMIN",
        "status": "active",
        "last_active": "2026-04-12T10:00:00Z",
        "created_at": "2025-01-15T09:00:00Z",
    },
    {
        "user_id": "usr-ops-001",
        "email": "ops@nakodacraft.com",
        "display_name": "Ops Manager",
        "role": "OPS",
        "status": "active",
        "last_active": "2026-04-11T16:30:00Z",
        "created_at": "2025-02-20T09:00:00Z",
    },
    {
        "user_id": "usr-comp-001",
        "email": "compliance@nakodacraft.com",
        "display_name": "Compliance Officer",
        "role": "COMPLIANCE",
        "status": "active",
        "last_active": "2026-04-10T14:15:00Z",
        "created_at": "2025-03-10T09:00:00Z",
    },
    {
        "user_id": "usr-ext-001",
        "email": "importer@acme.com",
        "display_name": "Acme Importer",
        "role": "EXTERNAL",
        "status": "active",
        "last_active": "2026-04-09T11:00:00Z",
        "created_at": "2025-06-01T09:00:00Z",
    },
]

_SSO_CONFIG = {
    "oidc_google_enabled": False,
    "oidc_google_client_id": None,
    "saml_microsoft_enabled": False,
    "saml_microsoft_entity_id": None,
}

_next_user_id = 5


# ── Routes ──────────────────────────────────────────────────────────────────


@router.get("/users", response_model=UserListResponse)
async def list_users(
    role: Optional[str] = Query(None, description="Filter by role"),
    status: Optional[str] = Query(None, description="Filter by status"),
) -> UserListResponse:
    """List all users with optional role/status filtering."""
    users = _STUB_USERS
    if role:
        users = [u for u in users if u["role"] == role]
    if status:
        users = [u for u in users if u["status"] == status]
    return UserListResponse(
        users=[UserResponse(**u) for u in users],
        total=len(users),
    )


@router.post("/users/invite", response_model=InviteUserResponse, status_code=201)
async def invite_user(req: InviteUserRequest) -> InviteUserResponse:
    """Invite a new user by email."""
    global _next_user_id

    # Check for duplicate email
    if any(u["email"] == req.email for u in _STUB_USERS):
        raise HTTPException(status_code=409, detail="User with this email already exists")

    # Validate role
    valid_roles = {r.value for r in Role}
    if req.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")

    user_id = f"usr-new-{_next_user_id:03d}"
    _next_user_id += 1

    _STUB_USERS.append({
        "user_id": user_id,
        "email": req.email,
        "display_name": req.display_name,
        "role": req.role,
        "status": "invited",
        "last_active": None,
        "created_at": "2026-04-12T12:00:00Z",
    })

    log_auth_event("admin.user_invited", f"Invited {req.email} as {req.role}")

    return InviteUserResponse(
        user_id=user_id,
        email=req.email,
        message=f"Invitation sent to {req.email}",
    )


@router.patch("/users/{user_id}/role")
async def update_user_role(user_id: str, req: UpdateRoleRequest) -> dict:
    """Update a user's role."""
    valid_roles = {r.value for r in Role}
    if req.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")

    user = next((u for u in _STUB_USERS if u["user_id"] == user_id), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_role = user["role"]
    user["role"] = req.role
    log_auth_event("admin.role_changed", f"{user['email']}: {old_role} → {req.role}")

    return {"user_id": user_id, "role": req.role, "message": "Role updated"}


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(user_id: str) -> dict:
    """Deactivate a user account."""
    user = next((u for u in _STUB_USERS if u["user_id"] == user_id), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user["status"] = "deactivated"
    log_auth_event("admin.user_deactivated", f"Deactivated {user['email']}")

    return {"user_id": user_id, "status": "deactivated", "message": "User deactivated"}


@router.post("/users/{user_id}/activate")
async def activate_user(user_id: str) -> dict:
    """Reactivate a deactivated user account."""
    user = next((u for u in _STUB_USERS if u["user_id"] == user_id), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user["status"] = "active"
    log_auth_event("admin.user_activated", f"Activated {user['email']}")

    return {"user_id": user_id, "status": "active", "message": "User activated"}


@router.get("/sso", response_model=SSOConfigResponse)
async def get_sso_config() -> SSOConfigResponse:
    """Get current SSO configuration."""
    return SSOConfigResponse(**_SSO_CONFIG)


@router.put("/sso")
async def update_sso_config(req: UpdateSSOConfigRequest) -> dict:
    """Update SSO configuration."""
    if req.oidc_google_enabled is not None:
        _SSO_CONFIG["oidc_google_enabled"] = req.oidc_google_enabled
    if req.oidc_google_client_id is not None:
        _SSO_CONFIG["oidc_google_client_id"] = req.oidc_google_client_id
    if req.saml_microsoft_enabled is not None:
        _SSO_CONFIG["saml_microsoft_enabled"] = req.saml_microsoft_enabled
    if req.saml_microsoft_entity_id is not None:
        _SSO_CONFIG["saml_microsoft_entity_id"] = req.saml_microsoft_entity_id

    log_auth_event("admin.sso_updated", "SSO configuration updated")

    return {"message": "SSO configuration updated", **_SSO_CONFIG}
