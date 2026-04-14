"""Tests for document API endpoints — upload, list, get, preview, classify."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_documents():
    """Reset document registry between tests to avoid side-effects."""
    import labelforge.api.v1.documents as docs_mod
    original = list(docs_mod._documents)
    yield
    docs_mod._documents.clear()
    docs_mod._documents.extend(original)


class TestListDocuments:
    def test_returns_documents(self, client, admin_headers):
        resp = client.get("/api/v1/documents", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "documents" in data
        assert "total" in data
        assert data["total"] >= 4

    def test_filter_by_order_id(self, client, admin_headers):
        resp = client.get("/api/v1/documents", params={"order_id": "ORD-2026-0042"}, headers=admin_headers)
        assert resp.status_code == 200
        for doc in resp.json()["documents"]:
            assert doc["order_id"] == "ORD-2026-0042"

    def test_filter_by_doc_class(self, client, admin_headers):
        resp = client.get("/api/v1/documents", params={"doc_class": "PURCHASE_ORDER"}, headers=admin_headers)
        assert resp.status_code == 200
        for doc in resp.json()["documents"]:
            assert doc["doc_class"] == "PURCHASE_ORDER"

    def test_filter_by_classification_status(self, client, admin_headers):
        resp = client.get("/api/v1/documents", params={"classification_status": "classified"}, headers=admin_headers)
        assert resp.status_code == 200
        for doc in resp.json()["documents"]:
            assert doc["classification_status"] == "classified"

    def test_pagination(self, client, admin_headers):
        resp = client.get("/api/v1/documents", params={"limit": 2}, headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["documents"]) <= 2


class TestGetDocument:
    def test_get_existing(self, client, admin_headers):
        resp = client.get("/api/v1/documents/doc-001", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "doc-001"
        assert "storage_key" in data

    def test_get_not_found(self, client, admin_headers):
        resp = client.get("/api/v1/documents/doc-999", headers=admin_headers)
        assert resp.status_code == 404


class TestUploadDocument:
    def test_upload_success(self, client, admin_headers):
        resp = client.post(
            "/api/v1/documents/upload",
            params={"order_id": "ORD-2026-0042"},
            files={"file": ("test-PO.pdf", b"fake pdf content", "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["filename"] == "test-PO.pdf"
        assert data["doc_class"] == "PURCHASE_ORDER"
        assert data["classification_status"] == "pending"
        assert data["size_bytes"] > 0

    def test_upload_stores_in_blobstore(self, client, admin_headers):
        resp = client.post(
            "/api/v1/documents/upload",
            params={"order_id": "ORD-2026-0042"},
            files={"file": ("PI-test.pdf", b"pi content", "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        doc_id = resp.json()["id"]
        # Verify document appears in listing
        list_resp = client.get("/api/v1/documents", headers=admin_headers)
        ids = [d["id"] for d in list_resp.json()["documents"]]
        assert doc_id in ids

    def test_upload_empty_file_rejected(self, client, admin_headers):
        resp = client.post(
            "/api/v1/documents/upload",
            params={"order_id": "ORD-2026-0042"},
            files={"file": ("empty.pdf", b"", "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_upload_classification_by_filename(self, client, admin_headers):
        """Files with recognized names get quick classification."""
        cases = [
            ("PO-12345.pdf", "PURCHASE_ORDER"),
            ("proforma-invoice.pdf", "PROFORMA_INVOICE"),
            ("protocol_v3.pdf", "PROTOCOL"),
            ("warning-labels.pdf", "WARNING_LABELS"),
            ("checklist.pdf", "CHECKLIST"),
            ("random-file.pdf", "UNKNOWN"),
        ]
        for filename, expected_class in cases:
            resp = client.post(
                "/api/v1/documents/upload",
                params={"order_id": "ORD-2026-0042"},
                files={"file": (filename, b"content", "application/pdf")},
                headers=admin_headers,
            )
            assert resp.status_code == 201
            assert resp.json()["doc_class"] == expected_class, f"Failed for {filename}"

    def test_upload_requires_auth(self, client):
        resp = client.post(
            "/api/v1/documents/upload",
            params={"order_id": "ORD-2026-0042"},
            files={"file": ("test.pdf", b"content", "application/pdf")},
        )
        assert resp.status_code == 401


class TestPreviewDocument:
    def test_preview_not_found(self, client, admin_headers):
        resp = client.get("/api/v1/documents/doc-999/preview", headers=admin_headers)
        assert resp.status_code == 404

    def test_preview_uploaded_document(self, client, admin_headers):
        """Upload a file then preview it — should return the same content."""
        content = b"test pdf bytes"
        client.post(
            "/api/v1/documents/upload",
            params={"order_id": "ORD-2026-0042"},
            files={"file": ("test.pdf", content, "application/pdf")},
            headers=admin_headers,
        )
        # Find the uploaded doc
        docs = client.get("/api/v1/documents", headers=admin_headers).json()["documents"]
        uploaded = [d for d in docs if d["filename"] == "test.pdf"]
        assert len(uploaded) > 0
        doc_id = uploaded[0]["id"]

        resp = client.get(f"/api/v1/documents/{doc_id}/preview", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.content == content


class TestDocumentResponse:
    def test_document_has_required_fields(self, client, admin_headers):
        resp = client.get("/api/v1/documents", headers=admin_headers)
        doc = resp.json()["documents"][0]
        required = ["id", "order_id", "filename", "doc_class", "confidence",
                     "size_bytes", "page_count", "uploaded_at", "classification_status"]
        for field in required:
            assert field in doc, f"Missing field: {field}"

    def test_detail_has_storage_key(self, client, admin_headers):
        resp = client.get("/api/v1/documents/doc-001", headers=admin_headers)
        assert "storage_key" in resp.json()


class TestOrderDocumentUpload:
    def test_upload_to_order(self, client, admin_headers):
        resp = client.post(
            "/api/v1/orders/ORD-2026-0042/documents",
            files={"file": ("PO-new.pdf", b"order doc", "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["order_id"] == "ORD-2026-0042"
        assert data["filename"] == "PO-new.pdf"
        assert data["classification_status"] == "pending"

    def test_upload_to_nonexistent_order(self, client, admin_headers):
        resp = client.post(
            "/api/v1/orders/ORD-NONEXISTENT/documents",
            files={"file": ("test.pdf", b"content", "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 404
