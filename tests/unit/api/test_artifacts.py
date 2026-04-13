"""Tests for artifact gallery API endpoints."""
from __future__ import annotations

import pytest

PREFIX = "/api/v1/artifacts"


class TestListArtifacts:
    def test_returns_artifacts(self, client, admin_headers):
        resp = client.get(PREFIX, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "artifacts" in data
        assert "total" in data
        assert len(data["artifacts"]) == 3

    def test_artifact_structure(self, client, admin_headers):
        resp = client.get(PREFIX, headers=admin_headers)
        art = resp.json()["artifacts"][0]
        assert "artifact_id" in art
        assert "artifact_type" in art
        assert "content_hash" in art

    def test_filter_by_type(self, client, admin_headers):
        resp = client.get(PREFIX, params={"artifact_type": "die_cut_svg"}, headers=admin_headers)
        assert resp.status_code == 200
        for art in resp.json()["artifacts"]:
            assert art["artifact_type"] == "die_cut_svg"

    def test_search_by_id(self, client, admin_headers):
        resp = client.get(PREFIX, params={"search": "art-002"}, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["artifacts"][0]["artifact_id"] == "art-002"

    def test_search_by_hash(self, client, admin_headers):
        resp = client.get(PREFIX, params={"search": "abcdef"}, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_filter_by_order_id(self, client, admin_headers):
        resp = client.get(PREFIX, params={"order_id": "ORD-2026-0042"}, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_pagination_limit(self, client, admin_headers):
        resp = client.get(PREFIX, params={"limit": 1}, headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["artifacts"]) == 1

    def test_pagination_offset(self, client, admin_headers):
        resp = client.get(PREFIX, params={"offset": 2}, headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["artifacts"]) == 1


class TestGetArtifact:
    def test_get_existing(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/art-001", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["artifact_id"] == "art-001"
        assert "size_bytes" in data
        assert "mime_type" in data
        assert "storage_key" in data
        assert "order_id" in data
        assert "created_by" in data

    def test_get_not_found(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/art-999", headers=admin_headers)
        assert resp.status_code == 404


class TestProvenance:
    def test_get_provenance_chain(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/art-001/provenance", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["artifact_id"] == "art-001"
        assert len(data["steps"]) == 3

    def test_provenance_step_structure(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/art-001/provenance", headers=admin_headers)
        step = resp.json()["steps"][0]
        for field in ("step_number", "agent_id", "input_hash", "output_hash",
                      "action", "timestamp", "duration_ms"):
            assert field in step

    def test_provenance_ordered(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/art-001/provenance", headers=admin_headers)
        steps = resp.json()["steps"]
        assert [s["step_number"] for s in steps] == [1, 2, 3]

    def test_provenance_not_found(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/art-999/provenance", headers=admin_headers)
        assert resp.status_code == 404


class TestDownload:
    def test_download_returns_url(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/art-003/download", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "download_url" in data
        assert data["download_url"].startswith("https://")
        assert data["filename"] == "diecut.svg"
        assert data["mime_type"] == "image/svg+xml"
        assert data["size_bytes"] > 0

    def test_download_not_found(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/art-999/download", headers=admin_headers)
        assert resp.status_code == 404
