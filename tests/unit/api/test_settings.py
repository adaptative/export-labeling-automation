"""Tests for settings API endpoints — profile, password, MFA."""
from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from labelforge.app import app


@pytest.fixture(autouse=True)
def _reset_stub_state():
    """Reset stub data between tests."""
    import labelforge.api.v1.settings as settings_mod

    original_profile = dict(settings_mod._STUB_PROFILE)
    original_hash = settings_mod._STUB_PASSWORD_HASH
    original_mfa = settings_mod._MFA_ENABLED
    original_method = settings_mod._MFA_METHOD
    yield
    settings_mod._STUB_PROFILE.clear()
    settings_mod._STUB_PROFILE.update(original_profile)
    settings_mod._STUB_PASSWORD_HASH = original_hash
    settings_mod._MFA_ENABLED = original_mfa
    settings_mod._MFA_METHOD = original_method


@pytest.fixture
def client():
    return TestClient(app)


# ── Profile ─────────────────────────────────────────────────────────────────


class TestProfile:
    def test_get_profile(self, client):
        resp = client.get("/api/v1/settings/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "admin@nakodacraft.com"
        assert data["display_name"] == "Admin User"
        assert "timezone" in data
        assert "language" in data

    def test_update_profile_name(self, client):
        resp = client.patch("/api/v1/settings/profile", json={
            "display_name": "Updated Admin",
        })
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Updated Admin"

    def test_update_profile_phone(self, client):
        resp = client.patch("/api/v1/settings/profile", json={
            "phone": "+1-555-0100",
        })
        assert resp.status_code == 200
        assert resp.json()["phone"] == "+1-555-0100"

    def test_update_profile_timezone(self, client):
        resp = client.patch("/api/v1/settings/profile", json={
            "timezone": "Asia/Kolkata",
        })
        assert resp.status_code == 200
        assert resp.json()["timezone"] == "Asia/Kolkata"

    def test_update_profile_persists(self, client):
        client.patch("/api/v1/settings/profile", json={"display_name": "Changed"})
        resp = client.get("/api/v1/settings/profile")
        assert resp.json()["display_name"] == "Changed"


# ── Password ────────────────────────────────────────────────────────────────


class TestPassword:
    def test_change_password_success(self, client):
        resp = client.post("/api/v1/settings/password", json={
            "current_password": "admin123",
            "new_password": "newpass1234",
        })
        assert resp.status_code == 200
        assert "changed" in resp.json()["message"].lower()

    def test_change_password_wrong_current(self, client):
        resp = client.post("/api/v1/settings/password", json={
            "current_password": "wrongpassword",
            "new_password": "newpass1234",
        })
        assert resp.status_code == 400

    def test_change_password_too_short(self, client):
        resp = client.post("/api/v1/settings/password", json={
            "current_password": "admin123",
            "new_password": "short",
        })
        assert resp.status_code == 400


# ── MFA ─────────────────────────────────────────────────────────────────────


class TestMFA:
    def test_get_mfa_status_disabled(self, client):
        resp = client.get("/api/v1/settings/mfa")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_enable_mfa_returns_secret(self, client):
        resp = client.post("/api/v1/settings/mfa/enable", json={"method": "totp"})
        assert resp.status_code == 200
        data = resp.json()
        assert "secret" in data
        assert "qr_uri" in data
        assert "otpauth://" in data["qr_uri"]

    def test_enable_mfa_unsupported_method(self, client):
        resp = client.post("/api/v1/settings/mfa/enable", json={"method": "sms"})
        assert resp.status_code == 400

    def test_verify_mfa_valid_code(self, client):
        client.post("/api/v1/settings/mfa/enable", json={"method": "totp"})
        resp = client.post("/api/v1/settings/mfa/verify", json={"code": "123456"})
        assert resp.status_code == 200
        # Verify MFA is now enabled
        status = client.get("/api/v1/settings/mfa").json()
        assert status["enabled"] is True
        assert status["method"] == "totp"

    def test_verify_mfa_invalid_code(self, client):
        client.post("/api/v1/settings/mfa/enable", json={"method": "totp"})
        resp = client.post("/api/v1/settings/mfa/verify", json={"code": "000000"})
        assert resp.status_code == 400

    def test_disable_mfa(self, client):
        # Enable first
        client.post("/api/v1/settings/mfa/enable", json={"method": "totp"})
        client.post("/api/v1/settings/mfa/verify", json={"code": "123456"})
        # Disable
        resp = client.post("/api/v1/settings/mfa/disable")
        assert resp.status_code == 200
        # Verify disabled
        status = client.get("/api/v1/settings/mfa").json()
        assert status["enabled"] is False

    def test_disable_mfa_when_not_enabled(self, client):
        resp = client.post("/api/v1/settings/mfa/disable")
        assert resp.status_code == 400

    def test_enable_mfa_when_already_enabled(self, client):
        client.post("/api/v1/settings/mfa/enable", json={"method": "totp"})
        client.post("/api/v1/settings/mfa/verify", json={"code": "123456"})
        resp = client.post("/api/v1/settings/mfa/enable", json={"method": "totp"})
        assert resp.status_code == 400


# ── Schema check ────────────────────────────────────────────────────────────


class TestSettingsSchema:
    def test_settings_paths_in_openapi(self, client):
        resp = client.get("/api/v1/openapi.json")
        paths = resp.json()["paths"]
        assert "/api/v1/settings/profile" in paths
        assert "/api/v1/settings/password" in paths
        assert "/api/v1/settings/mfa" in paths
        assert "/api/v1/settings/mfa/enable" in paths
        assert "/api/v1/settings/mfa/verify" in paths
        assert "/api/v1/settings/mfa/disable" in paths
