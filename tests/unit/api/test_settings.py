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


# ── Profile ─────────────────────────────────────────────────────────────────


class TestProfile:
    def test_get_profile(self, client, admin_headers):
        resp = client.get("/api/v1/settings/profile", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "admin@nakodacraft.com"
        assert data["display_name"] == "Admin User"
        assert "timezone" in data
        assert "language" in data

    def test_update_profile_name(self, client, admin_headers):
        resp = client.patch("/api/v1/settings/profile", json={
            "display_name": "Updated Admin",
        }, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Updated Admin"

    def test_update_profile_phone(self, client, admin_headers):
        resp = client.patch("/api/v1/settings/profile", json={
            "phone": "+1-555-0100",
        }, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["phone"] == "+1-555-0100"

    def test_update_profile_timezone(self, client, admin_headers):
        resp = client.patch("/api/v1/settings/profile", json={
            "timezone": "Asia/Kolkata",
        }, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["timezone"] == "Asia/Kolkata"

    def test_update_profile_persists(self, client, admin_headers):
        client.patch("/api/v1/settings/profile", json={"display_name": "Changed"}, headers=admin_headers)
        resp = client.get("/api/v1/settings/profile", headers=admin_headers)
        assert resp.json()["display_name"] == "Changed"


# ── Password ────────────────────────────────────────────────────────────────


class TestPassword:
    def test_change_password_success(self, client, admin_headers):
        resp = client.post("/api/v1/settings/password", json={
            "current_password": "admin123",
            "new_password": "newpass1234",
        }, headers=admin_headers)
        assert resp.status_code == 200
        assert "changed" in resp.json()["message"].lower()

    def test_change_password_wrong_current(self, client, admin_headers):
        resp = client.post("/api/v1/settings/password", json={
            "current_password": "wrongpassword",
            "new_password": "newpass1234",
        }, headers=admin_headers)
        assert resp.status_code == 400

    def test_change_password_too_short(self, client, admin_headers):
        resp = client.post("/api/v1/settings/password", json={
            "current_password": "admin123",
            "new_password": "short",
        }, headers=admin_headers)
        assert resp.status_code == 400


# ── MFA ─────────────────────────────────────────────────────────────────────


class TestMFA:
    def test_get_mfa_status_disabled(self, client, admin_headers):
        resp = client.get("/api/v1/settings/mfa", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_enable_mfa_returns_secret(self, client, admin_headers):
        resp = client.post("/api/v1/settings/mfa/enable", json={"method": "totp"}, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "secret" in data
        assert "qr_uri" in data
        assert "otpauth://" in data["qr_uri"]

    def test_enable_mfa_unsupported_method(self, client, admin_headers):
        resp = client.post("/api/v1/settings/mfa/enable", json={"method": "sms"}, headers=admin_headers)
        assert resp.status_code == 400

    def test_verify_mfa_valid_code(self, client, admin_headers):
        client.post("/api/v1/settings/mfa/enable", json={"method": "totp"}, headers=admin_headers)
        resp = client.post("/api/v1/settings/mfa/verify", json={"code": "123456"}, headers=admin_headers)
        assert resp.status_code == 200
        status = client.get("/api/v1/settings/mfa", headers=admin_headers).json()
        assert status["enabled"] is True
        assert status["method"] == "totp"

    def test_verify_mfa_invalid_code(self, client, admin_headers):
        client.post("/api/v1/settings/mfa/enable", json={"method": "totp"}, headers=admin_headers)
        resp = client.post("/api/v1/settings/mfa/verify", json={"code": "000000"}, headers=admin_headers)
        assert resp.status_code == 400

    def test_disable_mfa(self, client, admin_headers):
        client.post("/api/v1/settings/mfa/enable", json={"method": "totp"}, headers=admin_headers)
        client.post("/api/v1/settings/mfa/verify", json={"code": "123456"}, headers=admin_headers)
        resp = client.post("/api/v1/settings/mfa/disable", headers=admin_headers)
        assert resp.status_code == 200
        status = client.get("/api/v1/settings/mfa", headers=admin_headers).json()
        assert status["enabled"] is False

    def test_disable_mfa_when_not_enabled(self, client, admin_headers):
        resp = client.post("/api/v1/settings/mfa/disable", headers=admin_headers)
        assert resp.status_code == 400

    def test_enable_mfa_when_already_enabled(self, client, admin_headers):
        client.post("/api/v1/settings/mfa/enable", json={"method": "totp"}, headers=admin_headers)
        client.post("/api/v1/settings/mfa/verify", json={"code": "123456"}, headers=admin_headers)
        resp = client.post("/api/v1/settings/mfa/enable", json={"method": "totp"}, headers=admin_headers)
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
