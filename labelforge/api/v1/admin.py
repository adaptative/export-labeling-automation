"""Admin API routes -- user management and SSO configuration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.core.auth import Role, TokenPayload, log_auth_event
from labelforge.db.session import get_db
from labelforge.db.models import User as UserModel, SSOConfig

router = APIRouter(prefix="/admin", tags=["admin"])


# -- Request / Response models ------------------------------------------------


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


# -- Helpers ------------------------------------------------------------------


def _user_to_response(u: UserModel) -> UserResponse:
    return UserResponse(
        user_id=u.id,
        email=u.email,
        display_name=u.display_name,
        role=u.role,
        status="active" if u.is_active else "deactivated",
        last_active=u.last_active.isoformat() if u.last_active else None,
        created_at=u.created_at.isoformat() if u.created_at else "",
    )


# -- Routes -------------------------------------------------------------------


@router.get("/users", response_model=UserListResponse)
async def list_users(
    role: Optional[str] = Query(None, description="Filter by role"),
    status: Optional[str] = Query(None, description="Filter by status"),
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """List all users with optional role/status filtering."""
    q = select(UserModel).where(UserModel.tenant_id == _user.tenant_id)

    if role:
        q = q.where(UserModel.role == role)
    if status == "active":
        q = q.where(UserModel.is_active.is_(True))
    elif status == "deactivated":
        q = q.where(UserModel.is_active.is_(False))

    result = await db.execute(q.order_by(UserModel.created_at))
    users = result.scalars().all()

    return UserListResponse(
        users=[_user_to_response(u) for u in users],
        total=len(users),
    )


@router.post("/users/invite", response_model=InviteUserResponse, status_code=201)
async def invite_user(
    req: InviteUserRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InviteUserResponse:
    """Invite a new user by email."""
    # Validate role
    valid_roles = {r.value for r in Role}
    if req.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")

    # Check for duplicate email within tenant
    existing = await db.execute(
        select(UserModel)
        .where(UserModel.tenant_id == _user.tenant_id)
        .where(UserModel.email == req.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User with this email already exists")

    user_id = str(uuid4())
    new_user = UserModel(
        id=user_id,
        tenant_id=_user.tenant_id,
        email=req.email,
        display_name=req.display_name,
        role=req.role,
        is_active=True,
    )
    db.add(new_user)
    await db.commit()

    log_auth_event("admin.user_invited", f"Invited {req.email} as {req.role}")

    return InviteUserResponse(
        user_id=user_id,
        email=req.email,
        message=f"Invitation sent to {req.email}",
    )


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    req: UpdateRoleRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update a user's role."""
    valid_roles = {r.value for r in Role}
    if req.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")

    result = await db.execute(
        select(UserModel)
        .where(UserModel.id == user_id)
        .where(UserModel.tenant_id == _user.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_role = user.role
    user.role = req.role
    await db.commit()

    log_auth_event("admin.role_changed", f"{user.email}: {old_role} -> {req.role}")

    return {"user_id": user_id, "role": req.role, "message": "Role updated"}


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Deactivate a user account."""
    result = await db.execute(
        select(UserModel)
        .where(UserModel.id == user_id)
        .where(UserModel.tenant_id == _user.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    await db.commit()

    log_auth_event("admin.user_deactivated", f"Deactivated {user.email}")

    return {"user_id": user_id, "status": "deactivated", "message": "User deactivated"}


@router.post("/users/{user_id}/activate")
async def activate_user(
    user_id: str,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reactivate a deactivated user account."""
    result = await db.execute(
        select(UserModel)
        .where(UserModel.id == user_id)
        .where(UserModel.tenant_id == _user.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = True
    await db.commit()

    log_auth_event("admin.user_activated", f"Activated {user.email}")

    return {"user_id": user_id, "status": "active", "message": "User activated"}


@router.get("/sso", response_model=SSOConfigResponse)
async def get_sso_config(
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SSOConfigResponse:
    """Get current SSO configuration."""
    result = await db.execute(
        select(SSOConfig).where(SSOConfig.tenant_id == _user.tenant_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        return SSOConfigResponse(
            oidc_google_enabled=False,
            oidc_google_client_id=None,
            saml_microsoft_enabled=False,
            saml_microsoft_entity_id=None,
        )

    return SSOConfigResponse(
        oidc_google_enabled=config.oidc_google_enabled,
        oidc_google_client_id=config.oidc_google_client_id,
        saml_microsoft_enabled=config.saml_microsoft_enabled,
        saml_microsoft_entity_id=config.saml_microsoft_entity_id,
    )


@router.put("/sso")
async def update_sso_config(
    req: UpdateSSOConfigRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update SSO configuration."""
    result = await db.execute(
        select(SSOConfig).where(SSOConfig.tenant_id == _user.tenant_id)
    )
    config = result.scalar_one_or_none()

    if not config:
        config = SSOConfig(
            id=str(uuid4()),
            tenant_id=_user.tenant_id,
        )
        db.add(config)

    if req.oidc_google_enabled is not None:
        config.oidc_google_enabled = req.oidc_google_enabled
    if req.oidc_google_client_id is not None:
        config.oidc_google_client_id = req.oidc_google_client_id
    if req.saml_microsoft_enabled is not None:
        config.saml_microsoft_enabled = req.saml_microsoft_enabled
    if req.saml_microsoft_entity_id is not None:
        config.saml_microsoft_entity_id = req.saml_microsoft_entity_id

    config.updated_at = datetime.now(timezone.utc)
    await db.commit()

    log_auth_event("admin.sso_updated", "SSO configuration updated")

    return {
        "message": "SSO configuration updated",
        "oidc_google_enabled": config.oidc_google_enabled,
        "oidc_google_client_id": config.oidc_google_client_id,
        "saml_microsoft_enabled": config.saml_microsoft_enabled,
        "saml_microsoft_entity_id": config.saml_microsoft_entity_id,
    }
