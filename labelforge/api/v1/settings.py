"""Settings API routes — profile update, password change, MFA."""
from __future__ import annotations

import hashlib
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from labelforge.api.v1.auth import get_current_user
from labelforge.core.auth import TokenPayload, log_auth_event

router = APIRouter(prefix="/settings", tags=["settings"])


# ── Request / Response models ────────────────────────────────────────────────


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


# ── Stub state ──────────────────────────────────────────────────────────────

_STUB_PROFILE = {
    "user_id": "usr-admin-001",
    "email": "admin@nakodacraft.com",
    "display_name": "Admin User",
    "phone": None,
    "timezone": "UTC",
    "language": "en",
}

_STUB_PASSWORD_HASH = hashlib.sha256(b"admin123").hexdigest()
_MFA_ENABLED = False
_MFA_METHOD: Optional[str] = None
_MFA_SECRET = "JBSWY3DPEHPK3PXP"  # Stub TOTP secret


# ── Routes ──────────────────────────────────────────────────────────────────


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(_user: TokenPayload = Depends(get_current_user)) -> ProfileResponse:
    """Get the current user's profile."""
    return ProfileResponse(**_STUB_PROFILE)


@router.patch("/profile", response_model=ProfileResponse)
async def update_profile(req: UpdateProfileRequest, _user: TokenPayload = Depends(get_current_user)) -> ProfileResponse:
    """Update the current user's profile."""
    if req.display_name is not None:
        _STUB_PROFILE["display_name"] = req.display_name
    if req.phone is not None:
        _STUB_PROFILE["phone"] = req.phone
    if req.timezone is not None:
        _STUB_PROFILE["timezone"] = req.timezone
    if req.language is not None:
        _STUB_PROFILE["language"] = req.language

    log_auth_event("settings.profile_updated", f"Profile updated for {_STUB_PROFILE['email']}")

    return ProfileResponse(**_STUB_PROFILE)


@router.post("/password")
async def change_password(req: ChangePasswordRequest, _user: TokenPayload = Depends(get_current_user)) -> dict:
    """Change the current user's password."""
    global _STUB_PASSWORD_HASH

    current_hash = hashlib.sha256(req.current_password.encode()).hexdigest()
    if current_hash != _STUB_PASSWORD_HASH:
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    _STUB_PASSWORD_HASH = hashlib.sha256(req.new_password.encode()).hexdigest()
    log_auth_event("settings.password_changed", "Password changed")

    return {"message": "Password changed successfully"}


@router.get("/mfa", response_model=MFAStatusResponse)
async def get_mfa_status(_user: TokenPayload = Depends(get_current_user)) -> MFAStatusResponse:
    """Get MFA status for the current user."""
    return MFAStatusResponse(enabled=_MFA_ENABLED, method=_MFA_METHOD)


@router.post("/mfa/enable", response_model=EnableMFAResponse)
async def enable_mfa(req: EnableMFARequest, _user: TokenPayload = Depends(get_current_user)) -> EnableMFAResponse:
    """Enable MFA — returns a TOTP secret and QR URI for setup."""
    if _MFA_ENABLED:
        raise HTTPException(status_code=400, detail="MFA is already enabled")

    if req.method not in ("totp",):
        raise HTTPException(status_code=400, detail=f"Unsupported MFA method: {req.method}")

    qr_uri = f"otpauth://totp/Labelforge:admin@nakodacraft.com?secret={_MFA_SECRET}&issuer=Labelforge"

    log_auth_event("settings.mfa_setup_started", f"MFA setup started (method={req.method})")

    return EnableMFAResponse(
        secret=_MFA_SECRET,
        qr_uri=qr_uri,
        message="Scan the QR code with your authenticator app, then verify with a code",
    )


@router.post("/mfa/verify")
async def verify_mfa(req: VerifyMFARequest, _user: TokenPayload = Depends(get_current_user)) -> dict:
    """Verify MFA code and finalize MFA enrollment."""
    global _MFA_ENABLED, _MFA_METHOD

    # Stub: accept "123456" as valid code
    if req.code != "123456":
        raise HTTPException(status_code=400, detail="Invalid verification code")

    _MFA_ENABLED = True
    _MFA_METHOD = "totp"
    log_auth_event("settings.mfa_enabled", "MFA enabled via TOTP")

    return {"message": "MFA enabled successfully", "method": "totp"}


@router.post("/mfa/disable")
async def disable_mfa(_user: TokenPayload = Depends(get_current_user)) -> dict:
    """Disable MFA for the current user."""
    global _MFA_ENABLED, _MFA_METHOD

    if not _MFA_ENABLED:
        raise HTTPException(status_code=400, detail="MFA is not enabled")

    _MFA_ENABLED = False
    _MFA_METHOD = None
    log_auth_event("settings.mfa_disabled", "MFA disabled")

    return {"message": "MFA disabled successfully"}
