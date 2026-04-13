"""Tests for admin API endpoints --- user management and SSO configuration."""
from __future__ import annotations

import pytest


# -- User listing ------------------------------------------------------------


class TestListUsers:
    def test_list_all_users(self, client, admin_headers):
        resp = client.get("/api/v1/admin/users", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 4
        assert len(data["users"]) == data["total"]

    def test_filter_by_role(self, client, admin_headers):
        resp = client.get("/api/v1/admin/users?role=ADMIN", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert all(u["role"] == "ADMIN" for u in data["users"])

    def test_filter_by_status(self, client, admin_headers):
        resp = client.get("/api/v1/admin/users?status=active", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert all(u["status"] == "active" for u in data["users"])

    def test_user_has_required_fields(self, client, admin_headers):
        resp = client.get("/api/v1/admin/users", headers=admin_headers)
        user = resp.json()["users"][0]
        assert "user_id" in user
        assert "email" in user
        assert "display_name" in user
        assert "role" in user
        assert "status" in user
        assert "created_at" in user


# -- User invitation ---------------------------------------------------------


class TestInviteUser:
    def test_invite_new_user(self, client, admin_headers):
        resp = client.post("/api/v1/admin/users/invite", json={
            "email": "newuser@example.com",
            "display_name": "New User",
            "role": "OPS",
        }, headers=admin_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "newuser@example.com"
        assert "user_id" in data

    def test_invite_duplicate_email(self, client, admin_headers):
        resp = client.post("/api/v1/admin/users/invite", json={
            "email": "admin@nakodacraft.com",
            "display_name": "Dup",
            "role": "OPS",
        }, headers=admin_headers)
        assert resp.status_code == 409

    def test_invite_invalid_role(self, client, admin_headers):
        resp = client.post("/api/v1/admin/users/invite", json={
            "email": "bad@example.com",
            "display_name": "Bad Role",
            "role": "SUPERADMIN",
        }, headers=admin_headers)
        assert resp.status_code == 400

    def test_invited_user_appears_in_list(self, client, admin_headers):
        client.post("/api/v1/admin/users/invite", json={
            "email": "listed@example.com",
            "display_name": "Listed User",
            "role": "COMPLIANCE",
        }, headers=admin_headers)
        resp = client.get("/api/v1/admin/users", headers=admin_headers)
        emails = [u["email"] for u in resp.json()["users"]]
        assert "listed@example.com" in emails


# -- Role update -------------------------------------------------------------


class TestUpdateRole:
    def test_update_role(self, client, admin_headers):
        resp = client.patch("/api/v1/admin/users/usr-ops-001/role", json={"role": "COMPLIANCE"}, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["role"] == "COMPLIANCE"

    def test_update_role_invalid(self, client, admin_headers):
        resp = client.patch("/api/v1/admin/users/usr-ops-001/role", json={"role": "FAKE"}, headers=admin_headers)
        assert resp.status_code == 400

    def test_update_role_user_not_found(self, client, admin_headers):
        resp = client.patch("/api/v1/admin/users/usr-nonexist/role", json={"role": "ADMIN"}, headers=admin_headers)
        assert resp.status_code == 404


# -- Deactivation / Activation -----------------------------------------------


class TestDeactivateActivate:
    def test_deactivate_user(self, client, admin_headers):
        resp = client.post("/api/v1/admin/users/usr-ops-001/deactivate", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "deactivated"

    def test_deactivate_not_found(self, client, admin_headers):
        resp = client.post("/api/v1/admin/users/usr-nonexist/deactivate", headers=admin_headers)
        assert resp.status_code == 404

    def test_activate_user(self, client, admin_headers):
        client.post("/api/v1/admin/users/usr-ops-001/deactivate", headers=admin_headers)
        resp = client.post("/api/v1/admin/users/usr-ops-001/activate", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_activate_not_found(self, client, admin_headers):
        resp = client.post("/api/v1/admin/users/usr-nonexist/activate", headers=admin_headers)
        assert resp.status_code == 404


# -- SSO configuration -------------------------------------------------------


class TestSSOConfig:
    def test_get_sso_config(self, client, admin_headers):
        resp = client.get("/api/v1/admin/sso", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "oidc_google_enabled" in data
        assert "saml_microsoft_enabled" in data

    def test_update_sso_config(self, client, admin_headers):
        resp = client.put("/api/v1/admin/sso", json={
            "oidc_google_enabled": True,
            "oidc_google_client_id": "google-client-123",
        }, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["oidc_google_enabled"] is True
        assert data["oidc_google_client_id"] == "google-client-123"

    def test_update_sso_partial(self, client, admin_headers):
        resp = client.put("/api/v1/admin/sso", json={
            "saml_microsoft_enabled": True,
        }, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["saml_microsoft_enabled"] is True


# -- Schema check ------------------------------------------------------------


class TestAdminSchema:
    def test_admin_paths_in_openapi(self, client):
        resp = client.get("/api/v1/openapi.json")
        paths = resp.json()["paths"]
        assert "/api/v1/admin/users" in paths
        assert "/api/v1/admin/users/invite" in paths
        assert "/api/v1/admin/sso" in paths
