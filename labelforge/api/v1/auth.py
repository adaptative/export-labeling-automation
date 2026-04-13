"""Authentication API routes — login, refresh, logout, SSO stubs."""
from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from labelforge.config import settings
from labelforge.core.auth import (
    AuthError,
    Capability,
    OIDCConfig,
    Role,
    ROLE_CAPABILITIES,
    SAMLConfig,
    TokenPayload,
    decode_token,
    log_auth_event,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Request / Response models ────────────────────────────────────────────────


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LogoutResponse(BaseModel):
    message: str = "Logged out successfully"


class SSORedirectResponse(BaseModel):
    redirect_url: str
    provider: str


# ── Auth dependency ─────────────────────────────────────────────────────────


async def get_current_user(request: Request) -> TokenPayload:
    """FastAPI dependency: extract and validate JWT from Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header[len("Bearer "):]
    try:
        return decode_token(token, settings.jwt_secret_key)
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_stub_jwt(user_id: str, tenant_id: str, role: str, email: str) -> str:
    """Create a stub JWT for development/testing."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=")
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "email": email,
        "capabilities": [c.value for c in ROLE_CAPABILITIES.get(Role(role), set())],
        "exp": time.time() + settings.jwt_expiration_minutes * 60,
        "iat": time.time(),
    }
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    sig = base64.urlsafe_b64encode(
        hashlib.sha256(f"{header.decode()}.{body.decode()}.{settings.jwt_secret_key}".encode()).digest()
    ).rstrip(b"=")
    return f"{header.decode()}.{body.decode()}.{sig.decode()}"


# Stub user database for development
STUB_USERS = {
    "admin@nakodacraft.com": {
        "user_id": "usr-admin-001",
        "tenant_id": "tnt-nakoda-001",
        "display_name": "Admin User",
        "role": "ADMIN",
        "password_hash": hashlib.sha256(b"admin123").hexdigest(),
    },
    "ops@nakodacraft.com": {
        "user_id": "usr-ops-001",
        "tenant_id": "tnt-nakoda-001",
        "display_name": "Ops Manager",
        "role": "OPS",
        "password_hash": hashlib.sha256(b"ops123").hexdigest(),
    },
    "compliance@nakodacraft.com": {
        "user_id": "usr-comp-001",
        "tenant_id": "tnt-nakoda-001",
        "display_name": "Compliance Officer",
        "role": "COMPLIANCE",
        "password_hash": hashlib.sha256(b"comp123").hexdigest(),
    },
    "importer@acme.com": {
        "user_id": "usr-ext-001",
        "tenant_id": "tnt-nakoda-001",
        "display_name": "Acme Importer",
        "role": "EXTERNAL",
        "password_hash": hashlib.sha256(b"portal123").hexdigest(),
        "portal_order_id": "ORD-2026-04-0042",
    },
}


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post("/login", response_model=LoginResponse, status_code=200)
async def login(req: LoginRequest) -> LoginResponse:
    """Authenticate user with email/password and return JWT."""
    user = STUB_USERS.get(req.email)
    if not user:
        log_auth_event("auth.login_failed", f"Unknown email: {req.email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    password_hash = hashlib.sha256(req.password.encode()).hexdigest()
    if password_hash != user["password_hash"]:
        log_auth_event("auth.login_failed", f"Wrong password for {req.email}", user_id=user["user_id"])
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = _make_stub_jwt(user["user_id"], user["tenant_id"], user["role"], req.email)
    expires_in = settings.jwt_expiration_minutes * 60

    log_auth_event("auth.login_success", f"Login: {req.email}", user_id=user["user_id"], tenant_id=user["tenant_id"])

    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        user={
            "user_id": user["user_id"],
            "email": req.email,
            "display_name": user["display_name"],
            "role": user["role"],
            "tenant_id": user["tenant_id"],
        },
    )


@router.post("/refresh", response_model=RefreshResponse, status_code=200)
async def refresh_token(current_user: TokenPayload = Depends(get_current_user)) -> RefreshResponse:
    """Refresh an access token using the current valid JWT."""
    # Look up user info from STUB_USERS to get email for new token
    email = ""
    for user_email, user_data in STUB_USERS.items():
        if user_data["user_id"] == current_user.user_id:
            email = user_email
            break
    if not email:
        raise HTTPException(status_code=401, detail="User not found")

    token = _make_stub_jwt(
        current_user.user_id, current_user.tenant_id,
        current_user.role.value, email,
    )
    return RefreshResponse(
        access_token=token,
        expires_in=settings.jwt_expiration_minutes * 60,
    )


@router.post("/logout", response_model=LogoutResponse, status_code=200)
async def logout() -> LogoutResponse:
    """Logout: revoke the current token.

    Stub: just logs the event. In production, adds token to Redis revocation list.
    """
    log_auth_event("auth.logout", "User logged out")
    return LogoutResponse()


@router.get("/oidc/{provider}/authorize", response_model=SSORedirectResponse)
async def oidc_authorize(provider: str) -> SSORedirectResponse:
    """Initiate OIDC login flow — redirect to identity provider."""
    if provider == "google":
        oidc = OIDCConfig(
            issuer_url="https://accounts.google.com",
            client_id="stub-client-id",
            redirect_uri=f"{settings.cors_origins.split(',')[0]}/api/v1/auth/oidc/google/callback",
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown OIDC provider: {provider}")

    try:
        url = oidc.get_authorization_url()
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    return SSORedirectResponse(redirect_url=url, provider=provider)


@router.get("/saml/{provider}/login", response_model=SSORedirectResponse)
async def saml_login(provider: str) -> SSORedirectResponse:
    """Initiate SAML login flow — redirect to identity provider."""
    if provider == "microsoft":
        saml = SAMLConfig(
            idp_metadata_url="https://login.microsoftonline.com/stub/metadata",
            sp_entity_id="labelforge",
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown SAML provider: {provider}")

    try:
        url = saml.get_login_url()
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    return SSORedirectResponse(redirect_url=url, provider=provider)


@router.get("/me")
async def get_me(current_user: TokenPayload = Depends(get_current_user)) -> dict:
    """Get the current authenticated user's info from the JWT."""
    # Look up display_name from STUB_USERS
    user_info = None
    email = ""
    for user_email, user_data in STUB_USERS.items():
        if user_data["user_id"] == current_user.user_id:
            user_info = user_data
            email = user_email
            break

    return {
        "user_id": current_user.user_id,
        "email": email,
        "display_name": user_info["display_name"] if user_info else "Unknown",
        "role": current_user.role.value,
        "tenant_id": current_user.tenant_id,
    }
