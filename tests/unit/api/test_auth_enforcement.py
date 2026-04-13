"""Tests that all protected endpoints reject unauthenticated requests.

Covers issue #135: All API endpoints return hardcoded mock data with no auth enforcement.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from labelforge.app import app

client = TestClient(app)


# All protected endpoints that must require auth
PROTECTED_ENDPOINTS = [
    # Orders
    ("GET", "/api/v1/orders"),
    ("GET", "/api/v1/orders/ORD-2026-0042"),
    ("GET", "/api/v1/orders/ORD-2026-0042/items"),
    # Items
    ("GET", "/api/v1/items"),
    ("GET", "/api/v1/items/item-001"),
    # Documents
    ("GET", "/api/v1/documents"),
    # Artifacts
    ("GET", "/api/v1/artifacts"),
    ("GET", "/api/v1/artifacts/art-001"),
    ("GET", "/api/v1/artifacts/art-001/provenance"),
    ("GET", "/api/v1/artifacts/art-001/download"),
    # Audit log
    ("GET", "/api/v1/audit-log"),
    ("GET", "/api/v1/audit-log/aud-001"),
    # Budgets
    ("GET", "/api/v1/budgets/current-spend"),
    ("GET", "/api/v1/budgets/events"),
    # HiTL
    ("GET", "/api/v1/hitl/threads"),
    ("GET", "/api/v1/hitl/threads/hitl-001"),
    # Rules
    ("GET", "/api/v1/rules"),
    ("GET", "/api/v1/rules/rule-001"),
    # Importers
    ("GET", "/api/v1/importers"),
    ("GET", "/api/v1/importers/IMP-ACME"),
    # Notifications
    ("GET", "/api/v1/notifications"),
    # Warning labels
    ("GET", "/api/v1/warning-labels"),
    # Admin
    ("GET", "/api/v1/admin/users"),
    ("GET", "/api/v1/admin/sso"),
    # Settings
    ("GET", "/api/v1/settings/profile"),
    ("GET", "/api/v1/settings/mfa"),
    # Auth (protected)
    ("GET", "/api/v1/auth/me"),
    ("POST", "/api/v1/auth/refresh"),
]


class TestNoTokenReturns401:
    """Every protected endpoint must return 401 without an Authorization header."""

    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_unauthenticated_request_rejected(self, method, path):
        if method == "GET":
            resp = client.get(path)
        elif method == "POST":
            resp = client.post(path)
        elif method == "PUT":
            resp = client.put(path)
        else:
            resp = client.request(method, path)

        assert resp.status_code == 401, (
            f"{method} {path} returned {resp.status_code} without auth, expected 401"
        )


class TestInvalidTokenReturns401:
    """Every protected endpoint must return 401 with an invalid JWT."""

    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_invalid_token_rejected(self, method, path):
        headers = {"Authorization": "Bearer invalid.token.here"}
        if method == "GET":
            resp = client.get(path, headers=headers)
        elif method == "POST":
            resp = client.post(path, headers=headers)
        elif method == "PUT":
            resp = client.put(path, headers=headers)
        else:
            resp = client.request(method, path, headers=headers)

        assert resp.status_code == 401, (
            f"{method} {path} returned {resp.status_code} with invalid token, expected 401"
        )


class TestMalformedAuthHeader:
    def test_missing_bearer_prefix(self):
        resp = client.get("/api/v1/orders", headers={"Authorization": "Token abc"})
        assert resp.status_code == 401

    def test_empty_bearer(self):
        resp = client.get("/api/v1/orders", headers={"Authorization": "Bearer "})
        assert resp.status_code == 401

    def test_no_auth_header(self):
        resp = client.get("/api/v1/orders")
        assert resp.status_code == 401


class TestValidTokenAllowsAccess:
    """A valid JWT should allow access to protected endpoints."""

    def test_admin_can_access_orders(self, admin_headers):
        resp = client.get("/api/v1/orders", headers=admin_headers)
        assert resp.status_code == 200

    def test_admin_can_access_artifacts(self, admin_headers):
        resp = client.get("/api/v1/artifacts", headers=admin_headers)
        assert resp.status_code == 200

    def test_admin_can_access_audit_log(self, admin_headers):
        resp = client.get("/api/v1/audit-log", headers=admin_headers)
        assert resp.status_code == 200

    def test_admin_can_access_budgets(self, admin_headers):
        resp = client.get("/api/v1/budgets/current-spend", headers=admin_headers)
        assert resp.status_code == 200

    def test_admin_can_access_admin_users(self, admin_headers):
        resp = client.get("/api/v1/admin/users", headers=admin_headers)
        assert resp.status_code == 200

    def test_ops_can_access_orders(self, ops_headers):
        resp = client.get("/api/v1/orders", headers=ops_headers)
        assert resp.status_code == 200


class TestAuthMeWithToken:
    """The /auth/me endpoint must return info from the JWT, not hardcoded data."""

    def test_returns_admin_info(self, admin_headers):
        resp = client.get("/api/v1/auth/me", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "usr-admin-001"
        assert data["email"] == "admin@nakodacraft.com"
        assert data["role"] == "ADMIN"

    def test_returns_ops_info(self, ops_headers):
        resp = client.get("/api/v1/auth/me", headers=ops_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "usr-ops-001"
        assert data["email"] == "ops@nakodacraft.com"
        assert data["role"] == "OPS"

    def test_rejects_without_token(self):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401


class TestAuthRefreshWithToken:
    """The /auth/refresh endpoint must validate the incoming token."""

    def test_refresh_with_valid_token(self, admin_headers):
        resp = client.post("/api/v1/auth/refresh", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["expires_in"] > 0

    def test_refresh_rejects_without_token(self):
        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401


class TestLoginStillPublic:
    """Login and other public endpoints must remain accessible without auth."""

    def test_login_endpoint_is_public(self):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nakodacraft.com", "password": "admin123"},
        )
        assert resp.status_code == 200

    def test_login_rejects_invalid_credentials(self):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "random@example.com", "password": "random123"},
        )
        assert resp.status_code == 401

    def test_health_check_is_public(self):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_ping_is_public(self):
        resp = client.get("/api/v1/ping")
        assert resp.status_code == 200

    def test_logout_is_public(self):
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 200
