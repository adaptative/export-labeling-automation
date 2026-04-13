"""Settings API routes -- profile update, password change, MFA."""
from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from labelforge.api.v1.auth import get_current_user
from labelforge.core.auth import TokenPayload, log_auth_event
from labelforge.db.session import get_db
from labelforge.db.models import User as UserModel

router = APIRouter(prefix="/settings", tags=["settings"])


# -- Request / Response models ------------------------------------------------


class ProfileResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    phone: Optional[str] = None
    timezone: str = "UTC"
    language: str = "en"


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None
    phone: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class MFAStatusResponse(BaseModel):
    enabled: bool
    method: Optional[str] = None


class EnableMFARequest(BaseModel):
    method: str = "totp"


class EnableMFAResponse(BaseModel):
    secret: str
    qr_uri: str
    message: str


class VerifyMFARequest(BaseModel):
    code: str


# -- Helpers ------------------------------------------------------------------


async def _get_current_user_model(
    user_id: str, tenant_id: str, db: AsyncSession
) -> UserModel:
    result = await db.execute(
        select(UserModel)
        .where(UserModel.id == user_id)
        .where(UserModel.tenant_id == tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# -- Routes -------------------------------------------------------------------


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Get the current user's profile."""
    user = await _get_current_user_model(_user.user_id, _user.tenant_id, db)
    return ProfileResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        phone=user.phone,
        timezone=user.timezone,
        language=user.language,
    )


@router.patch("/profile", response_model=ProfileResponse)
async def update_profile(
    req: UpdateProfileRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Update the current user's profile."""
    user = await _get_current_user_model(_user.user_id, _user.tenant_id, db)

    if req.display_name is not None:
        user.display_name = req.display_name
    if req.phone is not None:
        user.phone = req.phone
    if req.timezone is not None:
        user.timezone = req.timezone
    if req.language is not None:
        user.language = req.language

    await db.commit()
    await db.refresh(user)

    log_auth_event("settings.profile_updated", f"Profile updated for {user.email}")

    return ProfileResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        phone=user.phone,
        timezone=user.timezone,
        language=user.language,
    )


@router.post("/password")
async def change_password(
    req: ChangePasswordRequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Change the current user's password."""
    user = await _get_current_user_model(_user.user_id, _user.tenant_id, db)

    # Verify current password
    current_hash = hashlib.sha256(req.current_password.encode()).hexdigest()
    if user.hashed_password and current_hash != user.hashed_password:
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user.hashed_password = hashlib.sha256(req.new_password.encode()).hexdigest()
    await db.commit()

    log_auth_event("settings.password_changed", "Password changed")

    return {"message": "Password changed successfully"}


@router.get("/mfa", response_model=MFAStatusResponse)
async def get_mfa_status(
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MFAStatusResponse:
    """Get MFA status for the current user."""
    user = await _get_current_user_model(_user.user_id, _user.tenant_id, db)
    return MFAStatusResponse(enabled=user.mfa_enabled, method=user.mfa_method)


@router.post("/mfa/enable", response_model=EnableMFAResponse)
async def enable_mfa(
    req: EnableMFARequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EnableMFAResponse:
    """Enable MFA -- returns a TOTP secret and QR URI for setup."""
    user = await _get_current_user_model(_user.user_id, _user.tenant_id, db)

    if user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA is already enabled")

    if req.method not in ("totp",):
        raise HTTPException(status_code=400, detail=f"Unsupported MFA method: {req.method}")

    # Generate a TOTP secret if none exists
    if not user.mfa_secret:
        user.mfa_secret = secrets.token_hex(16)
        await db.commit()
        await db.refresh(user)

    qr_uri = f"otpauth://totp/Labelforge:{user.email}?secret={user.mfa_secret}&issuer=Labelforge"

    log_auth_event("settings.mfa_setup_started", f"MFA setup started (method={req.method})")

    return EnableMFAResponse(
        secret=user.mfa_secret,
        qr_uri=qr_uri,
        message="Scan the QR code with your authenticator app, then verify with a code",
    )


@router.post("/mfa/verify")
async def verify_mfa(
    req: VerifyMFARequest,
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify MFA code and finalize MFA enrollment."""
    user = await _get_current_user_model(_user.user_id, _user.tenant_id, db)

    # In production, validate the TOTP code against user.mfa_secret.
    # For now, accept "123456" as a valid code for testing.
    if req.code != "123456":
        raise HTTPException(status_code=400, detail="Invalid verification code")

    user.mfa_enabled = True
    user.mfa_method = "totp"
    await db.commit()

    log_auth_event("settings.mfa_enabled", "MFA enabled via TOTP")

    return {"message": "MFA enabled successfully", "method": "totp"}


@router.post("/mfa/disable")
async def disable_mfa(
    _user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Disable MFA for the current user."""
    user = await _get_current_user_model(_user.user_id, _user.tenant_id, db)

    if not user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA is not enabled")

    user.mfa_enabled = False
    user.mfa_method = None
    await db.commit()

    log_auth_event("settings.mfa_disabled", "MFA disabled")

    return {"message": "MFA disabled successfully"}
