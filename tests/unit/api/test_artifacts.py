"""Tests for artifact gallery API endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from labelforge.app import app

client = TestClient(app)
PREFIX = "/api/v1/artifacts"


class TestListArtifacts:
    def test_returns_artifacts(self):
        resp = client.get(PREFIX)
        assert resp.status_code == 200
        data = resp.json()
        assert "artifacts" in data
        assert "total" in data
        assert len(data["artifacts"]) == 3

    def test_artifact_structure(self):
        resp = client.get(PREFIX)
        art = resp.json()["artifacts"][0]
        assert "artifact_id" in art
        assert "artifact_type" in art
        assert "content_hash" in art

    def test_filter_by_type(self):
        resp = client.get(PREFIX, params={"artifact_type": "die_cut_svg"})
        assert resp.status_code == 200
        for art in resp.json()["artifacts"]:
            assert art["artifact_type"] == "die_cut_svg"

    def test_search_by_id(self):
        resp = client.get(PREFIX, params={"search": "art-002"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["artifacts"][0]["artifact_id"] == "art-002"

    def test_search_by_hash(self):
        resp = client.get(PREFIX, params={"search": "abcdef"})
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_filter_by_order_id(self):
        resp = client.get(PREFIX, params={"order_id": "PO-2065"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_pagination_limit(self):
        resp = client.get(PREFIX, params={"limit": 1})
        assert resp.status_code == 200
        assert len(resp.json()["artifacts"]) == 1

    def test_pagination_offset(self):
        resp = client.get(PREFIX, params={"offset": 2})
        assert resp.status_code == 200
        assert len(resp.json()["artifacts"]) == 1


class TestGetArtifact:
    def test_get_existing(self):
        resp = client.get(f"{PREFIX}/art-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["artifact_id"] == "art-001"
        assert "size_bytes" in data
        assert "mime_type" in data
        assert "storage_key" in data
        assert "order_id" in data
        assert "created_by" in data

    def test_get_not_found(self):
        resp = client.get(f"{PREFIX}/art-999")
        assert resp.status_code == 404


class TestProvenance:
    def test_get_provenance_chain(self):
        resp = client.get(f"{PREFIX}/art-001/provenance")
        assert resp.status_code == 200
        data = resp.json()
        assert data["artifact_id"] == "art-001"
        assert len(data["steps"]) == 3

    def test_provenance_step_structure(self):
        resp = client.get(f"{PREFIX}/art-001/provenance")
        step = resp.json()["steps"][0]
        for field in ("step_number", "agent_id", "input_hash", "output_hash",
                      "action", "timestamp", "duration_ms"):
            assert field in step

    def test_provenance_ordered(self):
        resp = client.get(f"{PREFIX}/art-001/provenance")
        steps = resp.json()["steps"]
        assert [s["step_number"] for s in steps] == [1, 2, 3]

    def test_provenance_not_found(self):
        resp = client.get(f"{PREFIX}/art-999/provenance")
        assert resp.status_code == 404


class TestDownload:
    def test_download_returns_url(self):
        resp = client.get(f"{PREFIX}/art-003/download")
        assert resp.status_code == 200
        data = resp.json()
        assert "download_url" in data
        assert data["download_url"].startswith("https://")
        assert data["filename"] == "diecut.svg"
        assert data["mime_type"] == "image/svg+xml"
        assert data["size_bytes"] > 0

    def test_download_not_found(self):
        resp = client.get(f"{PREFIX}/art-999/download")
        assert resp.status_code == 404
