"""Tests for importer CRUD + onboarding endpoints (Sprint 8)."""
from __future__ import annotations

import io


def _create_importer(client, headers, name="Acme Trading", code=None) -> str:
    body = {"name": name}
    if code:
        body["code"] = code
    resp = client.post("/api/v1/importers", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestImporterCRUD:
    def test_create_importer_success(self, client, admin_headers):
        resp = client.post(
            "/api/v1/importers",
            json={"name": "Acme Trading Co"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"].startswith("imp-")
        assert data["name"] == "Acme Trading Co"
        assert data["code"] == "acme-trading-co"

    def test_create_importer_with_explicit_code(self, client, admin_headers):
        resp = client.post(
            "/api/v1/importers",
            json={"name": "Acme", "code": "ACME-CUSTOM"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["code"] == "ACME-CUSTOM"

    def test_create_importer_duplicate_code_rejected(self, client, admin_headers):
        client.post("/api/v1/importers", json={"name": "Acme", "code": "dup"}, headers=admin_headers)
        resp = client.post(
            "/api/v1/importers",
            json={"name": "Acme2", "code": "dup"},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    def test_create_importer_requires_auth(self, client):
        resp = client.post("/api/v1/importers", json={"name": "X"})
        assert resp.status_code == 401

    def test_create_importer_empty_name_rejected(self, client, admin_headers):
        resp = client.post("/api/v1/importers", json={"name": "   "}, headers=admin_headers)
        assert resp.status_code == 400

    def test_list_importers_includes_created(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="Listable Co")
        resp = client.get("/api/v1/importers", headers=admin_headers)
        assert resp.status_code == 200
        ids = [i["importer_id"] for i in resp.json()["importers"]]
        assert imp_id in ids

    def test_get_importer_by_id(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="Detail Co")
        resp = client.get(f"/api/v1/importers/{imp_id}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["importer_id"] == imp_id

    def test_get_unknown_importer_404(self, client, admin_headers):
        resp = client.get("/api/v1/importers/imp-nope", headers=admin_headers)
        assert resp.status_code == 404

    def test_update_importer_name(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="Old Name")
        resp = client.put(
            f"/api/v1/importers/{imp_id}",
            json={"name": "New Name"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_update_importer_creates_new_profile_version(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="Profiled Co")
        resp = client.put(
            f"/api/v1/importers/{imp_id}",
            json={"brand_treatment": {"primary_color": "#ff0000"}},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 1
        assert data["brand_treatment"]["primary_color"] == "#ff0000"

        # Second update bumps version
        resp2 = client.put(
            f"/api/v1/importers/{imp_id}",
            json={"brand_treatment": {"primary_color": "#00ff00"}},
            headers=admin_headers,
        )
        assert resp2.json()["version"] == 2

    def test_soft_delete_importer(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="To Delete")
        resp = client.delete(f"/api/v1/importers/{imp_id}", headers=admin_headers)
        assert resp.status_code == 204

        # No longer in default list (which excludes inactive)
        list_resp = client.get("/api/v1/importers", headers=admin_headers)
        ids = [i["importer_id"] for i in list_resp.json()["importers"]]
        assert imp_id not in ids

        # Still retrievable with include_inactive
        incl = client.get("/api/v1/importers?include_inactive=true", headers=admin_headers)
        ids = [i["importer_id"] for i in incl.json()["importers"]]
        assert imp_id in ids


class TestImporterSubResources:
    def test_list_orders_empty(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="Orders Co")
        resp = client.get(f"/api/v1/importers/{imp_id}/orders", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json() == {"orders": [], "total": 0}

    def test_list_documents_empty(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="Docs Co")
        resp = client.get(f"/api/v1/importers/{imp_id}/documents", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json() == {"documents": [], "total": 0}

    def test_upload_document_and_list_and_delete(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="UploadCo")

        # Upload a protocol doc
        resp = client.post(
            f"/api/v1/importers/{imp_id}/documents/protocol",
            files={"file": ("protocol.pdf", io.BytesIO(b"%PDF-fake"), "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["doc_type"] == "protocol"
        assert data["version"] == 1

        # Upload a second version
        resp2 = client.post(
            f"/api/v1/importers/{imp_id}/documents/protocol",
            files={"file": ("protocol_v2.pdf", io.BytesIO(b"%PDF-fake-v2"), "application/pdf")},
            headers=admin_headers,
        )
        assert resp2.json()["version"] == 2

        # List returns both versions
        list_resp = client.get(
            f"/api/v1/importers/{imp_id}/documents", headers=admin_headers
        )
        assert list_resp.json()["total"] == 2

        # Delete removes the latest version
        del_resp = client.delete(
            f"/api/v1/importers/{imp_id}/documents/protocol", headers=admin_headers
        )
        assert del_resp.status_code == 204

        list_resp2 = client.get(
            f"/api/v1/importers/{imp_id}/documents", headers=admin_headers
        )
        assert list_resp2.json()["total"] == 1

    def test_upload_unknown_doc_type_rejected(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="BadType")
        resp = client.post(
            f"/api/v1/importers/{imp_id}/documents/bogus",
            files={"file": ("x.pdf", io.BytesIO(b"data"), "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_upload_empty_file_rejected(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="EmptyFile")
        resp = client.post(
            f"/api/v1/importers/{imp_id}/documents/protocol",
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_request_from_buyer_creates_notification(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="BuyerCo")
        resp = client.post(
            f"/api/v1/importers/{imp_id}/documents/protocol/request-from-buyer",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["doc_type"] == "protocol"
        assert body["notification_id"]

    def test_list_hitl_threads_empty(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="HiTLCo")
        resp = client.get(
            f"/api/v1/importers/{imp_id}/hitl-threads", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json() == {"threads": [], "total": 0}

    def test_list_rules_returns_tenant_rules(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="RulesCo")
        resp = client.get(f"/api/v1/importers/{imp_id}/rules", headers=admin_headers)
        assert resp.status_code == 200
        # Seed data may include tenant rules; assert the shape at least.
        body = resp.json()
        assert "rules" in body
        assert "total" in body


class TestOnboardingFlow:
    def test_start_onboarding_creates_session(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="OnbCo")
        resp = client.post(
            f"/api/v1/importers/{imp_id}/onboarding/start", headers=admin_headers
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "in_progress"
        assert body["session_id"].startswith("onb-")

    def test_start_onboarding_is_idempotent(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="Idempotent")
        r1 = client.post(f"/api/v1/importers/{imp_id}/onboarding/start", headers=admin_headers)
        r2 = client.post(f"/api/v1/importers/{imp_id}/onboarding/start", headers=admin_headers)
        assert r1.json()["session_id"] == r2.json()["session_id"]

    def test_extraction_before_upload_returns_404(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="NoUpload")
        resp = client.get(
            f"/api/v1/importers/{imp_id}/onboarding/extraction", headers=admin_headers
        )
        assert resp.status_code == 404

    def test_upload_and_poll_extraction(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="FullFlow")

        upload_resp = client.post(
            f"/api/v1/importers/{imp_id}/onboarding/upload",
            files=[
                ("files", ("protocol.pdf", io.BytesIO(b"%PDF-protocol"), "application/pdf")),
                ("files", ("warnings.pdf", io.BytesIO(b"%PDF-warnings"), "application/pdf")),
                ("files", ("checklist.pdf", io.BytesIO(b"%PDF-checklist"), "application/pdf")),
            ],
            headers=admin_headers,
        )
        assert upload_resp.status_code == 200, upload_resp.text
        data = upload_resp.json()
        assert set(data["uploaded_docs"]) == {"protocol", "warnings", "checklist"}

        # BackgroundTasks run on TestClient after response — poll extraction
        ext_resp = client.get(
            f"/api/v1/importers/{imp_id}/onboarding/extraction", headers=admin_headers
        )
        assert ext_resp.status_code == 200
        ext = ext_resp.json()
        assert set(ext["agents"].keys()) == {"protocol", "warnings", "checklist"}
        # With no LLM key, agents should have hit the deterministic fallback
        for key in ("protocol", "warnings", "checklist"):
            assert ext["agents"][key]["status"] in ("completed", "pending", "running")

    def test_finalize_creates_profile(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="FinalCo")
        resp = client.post(
            f"/api/v1/importers/{imp_id}/onboard/finalize",
            json={
                "brand_treatment": {"primary_color": "#123456"},
                "panel_layouts": {"carton_top": ["logo"]},
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["importer_id"] == imp_id
        assert body["profile_version"] == 1

        # Profile visible on GET
        get_resp = client.get(f"/api/v1/importers/{imp_id}", headers=admin_headers)
        assert get_resp.json()["brand_treatment"]["primary_color"] == "#123456"


class TestTenantIsolation:
    def test_importer_not_visible_cross_tenant(self, client, admin_headers):
        imp_id = _create_importer(client, admin_headers, name="SecretCo")

        # Build a token for a different tenant
        from labelforge.api.v1.auth import _make_stub_jwt

        other = _make_stub_jwt("usr-other-001", "tnt-other-001", "ADMIN", "other@x.com")
        other_headers = {"Authorization": f"Bearer {other}"}

        resp = client.get(f"/api/v1/importers/{imp_id}", headers=other_headers)
        assert resp.status_code == 404
