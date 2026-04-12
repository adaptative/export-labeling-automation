"""Tests for auth API routes — INT-002."""
from __future__ import annotations

from fastapi.testclient import TestClient

from labelforge.app import app

client = TestClient(app)


class TestLogin:
    def test_login_success(self):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nakodacraft.com", "password": "admin123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0
        assert data["user"]["email"] == "admin@nakodacraft.com"
        assert data["user"]["role"] == "ADMIN"

    def test_login_ops_user(self):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "ops@nakodacraft.com", "password": "ops123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["role"] == "OPS"

    def test_login_external_user(self):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "importer@acme.com", "password": "portal123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["role"] == "EXTERNAL"

    def test_login_wrong_password(self):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nakodacraft.com", "password": "wrongpass"},
        )
        assert resp.status_code == 401

    def test_login_unknown_email(self):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "pass"},
        )
        assert resp.status_code == 401

    def test_login_returns_valid_jwt_format(self):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nakodacraft.com", "password": "admin123"},
        )
        token = resp.json()["access_token"]
        parts = token.split(".")
        assert len(parts) == 3  # header.payload.signature


class TestRefresh:
    def test_refresh_returns_new_token(self):
        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["expires_in"] > 0


class TestLogout:
    def test_logout(self):
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Logged out successfully"


class TestOIDC:
    def test_google_oidc_authorize(self):
        resp = client.get("/api/v1/auth/oidc/google/authorize")
        assert resp.status_code == 200
        data = resp.json()
        assert "redirect_url" in data
        assert data["provider"] == "google"
        assert "authorize" in data["redirect_url"]

    def test_unknown_oidc_provider(self):
        resp = client.get("/api/v1/auth/oidc/unknown/authorize")
        assert resp.status_code == 400


class TestSAML:
    def test_microsoft_saml_login(self):
        resp = client.get("/api/v1/auth/saml/microsoft/login")
        assert resp.status_code == 200
        data = resp.json()
        assert "redirect_url" in data
        assert data["provider"] == "microsoft"

    def test_unknown_saml_provider(self):
        resp = client.get("/api/v1/auth/saml/unknown/login")
        assert resp.status_code == 400


class TestMe:
    def test_get_current_user(self):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data
        assert "email" in data
        assert "role" in data


class TestAuthPaths:
    """Verify auth paths appear in OpenAPI schema."""

    def test_auth_paths_in_schema(self):
        resp = client.get("/api/v1/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        paths = set(schema["paths"].keys())
        expected = {
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/logout",
            "/api/v1/auth/me",
        }
        missing = expected - paths
        assert not missing, f"Missing auth paths: {missing}"
