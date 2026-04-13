"""Tests for audit log API endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from labelforge.api.v1.auth import _make_stub_jwt
from labelforge.app import app

client = TestClient(app)
PREFIX = "/api/v1/audit-log"

_TOKEN = _make_stub_jwt("usr-admin-001", "tnt-nakoda-001", "ADMIN", "admin@nakodacraft.com")
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


class TestListAuditEntries:
    def test_returns_entries(self):
        resp = client.get(PREFIX, headers=_AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "total" in data
        assert len(data["entries"]) > 0

    def test_entry_structure(self):
        resp = client.get(PREFIX, headers=_AUTH)
        entry = resp.json()["entries"][0]
        for field in ("id", "timestamp", "actor", "actor_type", "action",
                      "resource_type", "resource_id", "detail", "ip_address"):
            assert field in entry

    def test_default_limit_20(self):
        resp = client.get(PREFIX, headers=_AUTH)
        assert resp.json()["limit"] == 20
        assert len(resp.json()["entries"]) <= 20

    def test_pagination_limit(self):
        resp = client.get(PREFIX, params={"limit": 5}, headers=_AUTH)
        assert resp.status_code == 200
        assert len(resp.json()["entries"]) == 5

    def test_pagination_offset(self):
        all_resp = client.get(PREFIX, params={"limit": 100}, headers=_AUTH)
        offset_resp = client.get(PREFIX, params={"offset": 3, "limit": 100}, headers=_AUTH)
        all_entries = all_resp.json()["entries"]
        offset_entries = offset_resp.json()["entries"]
        assert offset_entries[0]["id"] == all_entries[3]["id"]

    def test_search_by_actor(self):
        resp = client.get(PREFIX, params={"search": "sarah"}, headers=_AUTH)
        assert resp.status_code == 200
        for entry in resp.json()["entries"]:
            assert "sarah" in entry["actor"].lower() or "sarah" in entry["detail"].lower()

    def test_search_by_resource_id(self):
        resp = client.get(PREFIX, params={"search": "PO-2065"}, headers=_AUTH)
        assert resp.status_code == 200
        assert resp.json()["total"] > 0

    def test_filter_actor_type(self):
        resp = client.get(PREFIX, params={"actor_type": "agent"}, headers=_AUTH)
        assert resp.status_code == 200
        for entry in resp.json()["entries"]:
            assert entry["actor_type"] == "agent"

    def test_filter_action(self):
        resp = client.get(PREFIX, params={"action": "CREATE"}, headers=_AUTH)
        assert resp.status_code == 200
        for entry in resp.json()["entries"]:
            assert entry["action"] == "CREATE"

    def test_sort_desc_default(self):
        resp = client.get(PREFIX, params={"limit": 100}, headers=_AUTH)
        entries = resp.json()["entries"]
        timestamps = [e["timestamp"] for e in entries]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_sort_asc(self):
        resp = client.get(PREFIX, params={"sort_order": "asc", "limit": 100}, headers=_AUTH)
        entries = resp.json()["entries"]
        timestamps = [e["timestamp"] for e in entries]
        assert timestamps == sorted(timestamps)

    def test_combined_filters(self):
        resp = client.get(PREFIX, params={"actor_type": "user", "action": "APPROVE"}, headers=_AUTH)
        assert resp.status_code == 200
        for entry in resp.json()["entries"]:
            assert entry["actor_type"] == "user"
            assert entry["action"] == "APPROVE"


class TestGetAuditEntry:
    def test_get_existing(self):
        resp = client.get(f"{PREFIX}/aud-001", headers=_AUTH)
        assert resp.status_code == 200
        assert resp.json()["id"] == "aud-001"

    def test_get_not_found(self):
        resp = client.get(f"{PREFIX}/aud-999", headers=_AUTH)
        assert resp.status_code == 404

    def test_entry_has_metadata(self):
        resp = client.get(f"{PREFIX}/aud-001", headers=_AUTH)
        assert resp.status_code == 200
        assert resp.json()["metadata"] is not None
