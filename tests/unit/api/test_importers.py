"""Tests for importer onboarding API --- Sprint 6 / TASK-023."""
from __future__ import annotations

import uuid

import pytest


def _unique_code() -> str:
    """Generate a unique importer code to avoid UNIQUE constraint conflicts."""
    return f"T{uuid.uuid4().hex[:8].upper()}"


class TestCreateImporter:
    def test_create_importer_success(self, client, admin_headers):
        code = _unique_code()
        resp = client.post(
            "/api/v1/importers",
            json={"name": "Test Corp", "code": code},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Corp"
        assert data["code"] == code
        assert data["is_active"] is True
        assert data["id"]

    def test_create_importer_with_contact(self, client, admin_headers):
        code = _unique_code()
        resp = client.post(
            "/api/v1/importers",
            json={
                "name": "Contact Corp",
                "code": code,
                "contact_email": "info@contact.com",
                "contact_phone": "+1-555-1234",
                "address": "123 Main St",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["contact_email"] == "info@contact.com"
        assert data["contact_phone"] == "+1-555-1234"
        assert data["address"] == "123 Main St"

    def test_create_importer_requires_auth(self, client):
        resp = client.post(
            "/api/v1/importers",
            json={"name": "NoAuth Corp", "code": _unique_code()},
        )
        assert resp.status_code == 401

    def test_create_importer_missing_name(self, client, admin_headers):
        resp = client.post(
            "/api/v1/importers",
            json={"code": _unique_code()},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_create_importer_missing_code(self, client, admin_headers):
        resp = client.post(
            "/api/v1/importers",
            json={"name": "No Code"},
            headers=admin_headers,
        )
        assert resp.status_code == 422


class TestUpdateImporter:
    def test_update_importer_name(self, client, admin_headers):
        code = _unique_code()
        create_resp = client.post(
            "/api/v1/importers",
            json={"name": "UpdateMe Corp", "code": code},
            headers=admin_headers,
        )
        importer_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/v1/importers/{importer_id}",
            json={"name": "Updated Corp"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Corp"
        assert resp.json()["code"] == code

    def test_update_importer_contact_fields(self, client, admin_headers):
        code = _unique_code()
        create_resp = client.post(
            "/api/v1/importers",
            json={"name": "Fields Corp", "code": code},
            headers=admin_headers,
        )
        importer_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/v1/importers/{importer_id}",
            json={"contact_email": "new@test.com", "contact_phone": "+1-999"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["contact_email"] == "new@test.com"
        assert resp.json()["contact_phone"] == "+1-999"

    def test_update_nonexistent_importer(self, client, admin_headers):
        resp = client.put(
            "/api/v1/importers/nonexistent-id",
            json={"name": "Ghost"},
            headers=admin_headers,
        )
        assert resp.status_code == 404


class TestDeleteImporter:
    def test_soft_delete_importer(self, client, admin_headers):
        code = _unique_code()
        create_resp = client.post(
            "/api/v1/importers",
            json={"name": "DeleteMe Corp", "code": code},
            headers=admin_headers,
        )
        importer_id = create_resp.json()["id"]

        resp = client.delete(
            f"/api/v1/importers/{importer_id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Importer deactivated"

    def test_delete_nonexistent_importer(self, client, admin_headers):
        resp = client.delete(
            "/api/v1/importers/nonexistent-id",
            headers=admin_headers,
        )
        assert resp.status_code == 404


class TestOnboardingUpload:
    def test_upload_protocol_file(self, client, admin_headers):
        resp = client.post(
            "/api/v1/importers/IMP-ACME/onboarding/upload",
            files={"protocol": ("protocol.pdf", b"fake protocol content", "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["importer_id"] == "IMP-ACME"
        assert data["status"] == "processing_complete"
        assert len(data["documents"]) == 1
        assert data["documents"][0]["document_type"] == "protocol"

    def test_upload_all_files(self, client, admin_headers):
        resp = client.post(
            "/api/v1/importers/IMP-ACME/onboarding/upload",
            files={
                "protocol": ("protocol.pdf", b"fake protocol", "application/pdf"),
                "warnings": ("warnings.pdf", b"fake warnings", "application/pdf"),
                "checklist": ("checklist.pdf", b"fake checklist", "application/pdf"),
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["documents"]) == 3
        doc_types = {d["document_type"] for d in data["documents"]}
        assert doc_types == {"protocol", "warnings", "checklist"}

    def test_upload_for_nonexistent_importer(self, client, admin_headers):
        resp = client.post(
            "/api/v1/importers/NONEXISTENT/onboarding/upload",
            files={"protocol": ("protocol.pdf", b"content", "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_upload_requires_auth(self, client):
        resp = client.post(
            "/api/v1/importers/IMP-ACME/onboarding/upload",
            files={"protocol": ("protocol.pdf", b"content", "application/pdf")},
        )
        assert resp.status_code == 401


class TestExtractionStatus:
    def test_get_extraction_no_results(self, client, admin_headers):
        resp = client.get(
            "/api/v1/importers/IMP-GLOBEX/onboarding/extraction",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # May or may not have results depending on test ordering
        assert "status" in data

    def test_get_extraction_after_upload(self, client, admin_headers):
        # Upload first to a dedicated importer
        code = _unique_code()
        create_resp = client.post(
            "/api/v1/importers",
            json={"name": "Extract Corp", "code": code},
            headers=admin_headers,
        )
        importer_id = create_resp.json()["id"]

        client.post(
            f"/api/v1/importers/{importer_id}/onboarding/upload",
            files={
                "protocol": ("protocol.pdf", b"protocol content", "application/pdf"),
                "warnings": ("warnings.pdf", b"warnings content", "application/pdf"),
                "checklist": ("checklist.pdf", b"checklist content", "application/pdf"),
            },
            headers=admin_headers,
        )

        resp = client.get(
            f"/api/v1/importers/{importer_id}/onboarding/extraction",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["importer_id"] == importer_id
        assert len(data["results"]) == 3
        agent_ids = {r["agent_id"] for r in data["results"]}
        assert "agent-6.4-protocol-analyzer" in agent_ids
        assert "agent-6.5-warning-label-parser" in agent_ids
        assert "agent-6.6-checklist-extractor" in agent_ids

    def test_extraction_for_nonexistent_importer(self, client, admin_headers):
        resp = client.get(
            "/api/v1/importers/NONEXISTENT/onboarding/extraction",
            headers=admin_headers,
        )
        assert resp.status_code == 404


class TestFinalizeOnboarding:
    def test_finalize_creates_profile(self, client, admin_headers):
        code = _unique_code()
        create_resp = client.post(
            "/api/v1/importers",
            json={"name": "Finalize Corp", "code": code},
            headers=admin_headers,
        )
        importer_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/v1/importers/{importer_id}/onboard/finalize",
            json={
                "brand_treatment": {"color": "blue"},
                "panel_layouts": {"top": ["logo"]},
                "handling_symbol_rules": {"fragile": True},
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["importer_id"] == importer_id
        assert data["version"] == 1
        assert data["brand_treatment"] == {"color": "blue"}

    def test_finalize_increments_version(self, client, admin_headers):
        # Use IMP-ACME which already has version 3
        resp = client.post(
            "/api/v1/importers/IMP-ACME/onboard/finalize",
            json={
                "brand_treatment": {"color": "red"},
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        # version should be > 3 (exact value depends on test ordering)
        assert data["version"] > 3

    def test_finalize_nonexistent_importer(self, client, admin_headers):
        resp = client.post(
            "/api/v1/importers/NONEXISTENT/onboard/finalize",
            json={"brand_treatment": {}},
            headers=admin_headers,
        )
        assert resp.status_code == 404


class TestImporterOrders:
    def test_list_orders_for_importer(self, client, admin_headers):
        resp = client.get(
            "/api/v1/importers/IMP-ACME/orders",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2  # seed has 2 orders for ACME
        for order in data["orders"]:
            assert "id" in order

    def test_list_orders_empty(self, client, admin_headers):
        code = _unique_code()
        create_resp = client.post(
            "/api/v1/importers",
            json={"name": "NoOrders Corp", "code": code},
            headers=admin_headers,
        )
        importer_id = create_resp.json()["id"]

        resp = client.get(
            f"/api/v1/importers/{importer_id}/orders",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_orders_nonexistent_importer(self, client, admin_headers):
        resp = client.get(
            "/api/v1/importers/NONEXISTENT/orders",
            headers=admin_headers,
        )
        assert resp.status_code == 404


class TestImporterDocuments:
    def test_list_documents_for_importer(self, client, admin_headers):
        resp = client.get(
            "/api/v1/importers/IMP-ACME/documents",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2  # seed has 2 docs for ACME orders
        for doc in data["documents"]:
            assert "id" in doc
            assert "filename" in doc

    def test_list_documents_nonexistent_importer(self, client, admin_headers):
        resp = client.get(
            "/api/v1/importers/NONEXISTENT/documents",
            headers=admin_headers,
        )
        assert resp.status_code == 404
