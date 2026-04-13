"""Tests for audit log API endpoints."""
from __future__ import annotations

import pytest

PREFIX = "/api/v1/audit-log"


class TestListAuditEntries:
    def test_returns_entries(self, client, admin_headers):
        resp = client.get(PREFIX, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "total" in data
        assert len(data["entries"]) > 0

    def test_entry_structure(self, client, admin_headers):
        resp = client.get(PREFIX, headers=admin_headers)
        entry = resp.json()["entries"][0]
        for field in ("id", "timestamp", "actor", "actor_type", "action",
                      "resource_type", "resource_id", "detail", "ip_address"):
            assert field in entry

    def test_default_limit_20(self, client, admin_headers):
        resp = client.get(PREFIX, headers=admin_headers)
        assert resp.json()["limit"] == 20
        assert len(resp.json()["entries"]) <= 20

    def test_pagination_limit(self, client, admin_headers):
        resp = client.get(PREFIX, params={"limit": 5}, headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["entries"]) == 5

    def test_pagination_offset(self, client, admin_headers):
        all_resp = client.get(PREFIX, params={"limit": 100}, headers=admin_headers)
        offset_resp = client.get(PREFIX, params={"offset": 3, "limit": 100}, headers=admin_headers)
        all_entries = all_resp.json()["entries"]
        offset_entries = offset_resp.json()["entries"]
        assert offset_entries[0]["id"] == all_entries[3]["id"]

    def test_search_by_actor(self, client, admin_headers):
        resp = client.get(PREFIX, params={"search": "sarah"}, headers=admin_headers)
        assert resp.status_code == 200
        for entry in resp.json()["entries"]:
            assert "sarah" in entry["actor"].lower() or "sarah" in entry["detail"].lower()

    def test_search_by_resource_id(self, client, admin_headers):
        resp = client.get(PREFIX, params={"search": "PO-2065"}, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] > 0

    def test_filter_actor_type(self, client, admin_headers):
        resp = client.get(PREFIX, params={"actor_type": "agent"}, headers=admin_headers)
        assert resp.status_code == 200
        for entry in resp.json()["entries"]:
            assert entry["actor_type"] == "agent"

    def test_filter_action(self, client, admin_headers):
        resp = client.get(PREFIX, params={"action": "CREATE"}, headers=admin_headers)
        assert resp.status_code == 200
        for entry in resp.json()["entries"]:
            assert entry["action"] == "CREATE"

    def test_sort_desc_default(self, client, admin_headers):
        resp = client.get(PREFIX, params={"limit": 100}, headers=admin_headers)
        entries = resp.json()["entries"]
        timestamps = [e["timestamp"] for e in entries]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_sort_asc(self, client, admin_headers):
        resp = client.get(PREFIX, params={"sort_order": "asc", "limit": 100}, headers=admin_headers)
        entries = resp.json()["entries"]
        timestamps = [e["timestamp"] for e in entries]
        assert timestamps == sorted(timestamps)

    def test_combined_filters(self, client, admin_headers):
        resp = client.get(PREFIX, params={"actor_type": "user", "action": "APPROVE"}, headers=admin_headers)
        assert resp.status_code == 200
        for entry in resp.json()["entries"]:
            assert entry["actor_type"] == "user"
            assert entry["action"] == "APPROVE"


class TestGetAuditEntry:
    def test_get_existing(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/aud-001", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == "aud-001"

    def test_get_not_found(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/aud-999", headers=admin_headers)
        assert resp.status_code == 404

    def test_entry_has_metadata(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/aud-001", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["metadata"] is not None
