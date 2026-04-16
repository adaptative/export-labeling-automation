"""Tests for the Importer/Printer portal endpoints (INT-017, Sprint-13)."""
from __future__ import annotations

import asyncio
from typing import Optional
from uuid import uuid4

import pytest
from sqlalchemy import select

from labelforge.api.v1 import documents as docs_mod
from labelforge.core.blobstore import MemoryBlobStore
from labelforge.db import session as session_mod
from labelforge.db.models import Artifact, AuditLog, PortalToken


def _await(coro):
    """Drive an async coroutine from a sync test without relying on the
    ambient pytest event loop — which is unreliable across Python versions."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _create_token(client, admin_headers, *, role: str,
                  order_id: str = "ORD-2026-0042",
                  email: Optional[str] = None) -> str:
    resp = client.post(
        "/api/v1/portal/tokens",
        json={"order_id": order_id, "role": role, "email": email,
              "expires_in_hours": 24},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["token"]


# ── Token creation ─────────────────────────────────────────────────────────


class TestTokenCreation:
    def test_admin_can_create_importer_token(self, client, admin_headers):
        resp = client.post(
            "/api/v1/portal/tokens",
            json={"order_id": "ORD-2026-0042", "role": "importer",
                  "email": "client@acme.com", "expires_in_hours": 48},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["role"] == "importer"
        assert body["order_id"] == "ORD-2026-0042"
        assert body["status"] == "active"
        assert body["url_path"].endswith(body["token"])
        assert len(body["token"]) > 20  # urlsafe base64, 32 bytes

    def test_printer_role_supported(self, client, admin_headers):
        resp = client.post(
            "/api/v1/portal/tokens",
            json={"order_id": "ORD-2026-0042", "role": "printer"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "printer"

    def test_invalid_role_rejected(self, client, admin_headers):
        resp = client.post(
            "/api/v1/portal/tokens",
            json={"order_id": "ORD-2026-0042", "role": "carrier"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_unknown_order_404(self, client, admin_headers):
        resp = client.post(
            "/api/v1/portal/tokens",
            json={"order_id": "ORD-DOES-NOT-EXIST", "role": "importer"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        resp = client.post(
            "/api/v1/portal/tokens",
            json={"order_id": "ORD-2026-0042", "role": "importer"},
        )
        assert resp.status_code == 401


# ── Importer flow ───────────────────────────────────────────────────────────


class TestImporterPortal:
    def test_get_session_returns_order_details(self, client, admin_headers):
        token = _create_token(client, admin_headers, role="importer")
        resp = client.get(f"/api/v1/portal/importer/{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["role"] == "importer"
        assert body["status"] == "active"
        assert body["order"]["id"] == "ORD-2026-0042"
        assert body["order"]["po_number"] == "PO-88210"
        assert body["importer"]["code"] == "ACME"
        assert isinstance(body["items"], list)
        assert len(body["items"]) >= 1

    def test_get_session_with_wrong_role_is_404(self, client, admin_headers):
        token = _create_token(client, admin_headers, role="printer")
        resp = client.get(f"/api/v1/portal/importer/{token}")
        assert resp.status_code == 404

    def test_invalid_token_is_404(self, client):
        resp = client.get("/api/v1/portal/importer/not-a-real-token")
        assert resp.status_code == 404

    def test_approve_sets_status_and_records_audit(self, client, admin_headers):
        token = _create_token(client, admin_headers, role="importer",
                              email="client@acme.com")
        resp = client.post(
            f"/api/v1/portal/importer/{token}/approve",
            json={"approver_name": "Jane Importer",
                  "approver_email": "jane@acme.com",
                  "note": "Looks good"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body["status"] == "approved"

        async def _check():
            async with session_mod.async_session_factory() as db:
                row = (await db.execute(
                    select(PortalToken).where(PortalToken.token == token)
                )).scalar_one()
                assert row.status == "approved"
                assert row.action_taken_at is not None

                audits = (await db.execute(
                    select(AuditLog)
                    .where(AuditLog.resource_id == "ORD-2026-0042",
                           AuditLog.action == "portal_importer_approved")
                )).scalars().all()
                assert len(audits) == 1
                assert audits[0].actor_type == "portal"
                assert audits[0].actor == "jane@acme.com"
        _await(_check())

    def test_approve_twice_rejected_with_409(self, client, admin_headers):
        token = _create_token(client, admin_headers, role="importer")
        first = client.post(f"/api/v1/portal/importer/{token}/approve", json={})
        assert first.status_code == 200
        second = client.post(f"/api/v1/portal/importer/{token}/approve", json={})
        assert second.status_code == 409

    def test_reject_requires_reason(self, client, admin_headers):
        token = _create_token(client, admin_headers, role="importer")
        # Empty reason is a 422 validation error from pydantic min_length=1.
        resp = client.post(f"/api/v1/portal/importer/{token}/reject",
                           json={"reason": ""})
        assert resp.status_code == 422

    def test_reject_sets_status_and_note(self, client, admin_headers):
        token = _create_token(client, admin_headers, role="importer")
        resp = client.post(
            f"/api/v1/portal/importer/{token}/reject",
            json={"reason": "Logo position is wrong on carton_top",
                  "reviewer_name": "Bob"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_cannot_reject_after_approve(self, client, admin_headers):
        token = _create_token(client, admin_headers, role="importer")
        client.post(f"/api/v1/portal/importer/{token}/approve", json={})
        resp = client.post(f"/api/v1/portal/importer/{token}/reject",
                           json={"reason": "changed my mind"})
        assert resp.status_code == 409


# ── Printer flow ────────────────────────────────────────────────────────────


class TestPrinterPortal:
    def test_get_printer_session(self, client, admin_headers):
        token = _create_token(client, admin_headers, role="printer")
        resp = client.get(f"/api/v1/portal/printer/{token}")
        assert resp.status_code == 200
        assert resp.json()["role"] == "printer"

    def test_confirm_records_audit_and_terminal_status(self, client, admin_headers):
        token = _create_token(client, admin_headers, role="printer",
                              email="press@shop.com")
        resp = client.post(
            f"/api/v1/portal/printer/{token}/confirm",
            json={"printer_name": "PressBot", "note": "Received and printed"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"

        async def _check():
            async with session_mod.async_session_factory() as db:
                audits = (await db.execute(
                    select(AuditLog).where(
                        AuditLog.action == "portal_printer_confirmed",
                        AuditLog.resource_id == "ORD-2026-0042",
                    )
                )).scalars().all()
                assert len(audits) == 1
        _await(_check())

    def test_confirm_twice_rejected(self, client, admin_headers):
        token = _create_token(client, admin_headers, role="printer")
        client.post(f"/api/v1/portal/printer/{token}/confirm", json={})
        dup = client.post(f"/api/v1/portal/printer/{token}/confirm", json={})
        assert dup.status_code == 409

    def test_printer_token_cannot_access_importer_page(self, client, admin_headers):
        token = _create_token(client, admin_headers, role="printer")
        resp = client.get(f"/api/v1/portal/importer/{token}")
        assert resp.status_code == 404


# ── Printer bundle download (token-scoped) ──────────────────────────────────


@pytest.fixture
def mem_blob_store(monkeypatch):
    """In-memory blob store that both documents.py and portal.py read from."""
    store = MemoryBlobStore()
    monkeypatch.setattr(docs_mod, "_blob_store", store)
    return store


async def _plant_bundle_artifact(
    *, item_id: str, tenant_id: str, data: bytes, store: MemoryBlobStore,
) -> str:
    key = f"artifacts/bundle_zip/{uuid4()}.zip"
    meta = await store.upload(key, data, content_type="application/zip")
    aid = str(uuid4())
    async with session_mod.async_session_factory() as db:
        db.add(Artifact(
            id=aid, tenant_id=tenant_id, order_item_id=item_id,
            artifact_type="bundle_zip", s3_key=key,
            content_hash=meta.sha256, size_bytes=len(data),
            mime_type="application/zip", provenance={},
        ))
        await db.commit()
    return aid


class TestPrinterBundleDownload:
    def test_streams_bundle_zip_via_token(self, client, admin_headers, mem_blob_store):
        token = _create_token(client, admin_headers, role="printer")
        zip_body = b"PK\x03\x04" + b"fake-bundle-body"
        _await(_plant_bundle_artifact(
            item_id="item-001", tenant_id="tnt-nakoda-001",
            data=zip_body, store=mem_blob_store,
        ))
        # No auth headers — the token alone authenticates the download.
        resp = client.get(f"/api/v1/portal/printer/{token}/items/item-001/bundle")
        assert resp.status_code == 200
        assert resp.content == zip_body
        assert resp.headers["content-type"].startswith("application/zip")
        assert "attachment" in resp.headers["content-disposition"]

    def test_missing_bundle_returns_structured_404(self, client, admin_headers, mem_blob_store):
        token = _create_token(client, admin_headers, role="printer")
        resp = client.get(f"/api/v1/portal/printer/{token}/items/item-001/bundle")
        assert resp.status_code == 404
        assert resp.json().get("reason") == "not_generated"

    def test_wrong_order_item_404(self, client, admin_headers, mem_blob_store):
        # Mint token for a different order — item-001 is on ORD-2026-0042.
        resp = client.post(
            "/api/v1/portal/tokens",
            json={"order_id": "ORD-2026-0043", "role": "printer"},
            headers=admin_headers,
        )
        # If that order doesn't exist in the seed this will 404 — skip gracefully.
        if resp.status_code != 201:
            pytest.skip("Secondary order not seeded")
        other_token = resp.json()["token"]
        _await(_plant_bundle_artifact(
            item_id="item-001", tenant_id="tnt-nakoda-001",
            data=b"PK\x03\x04body", store=mem_blob_store,
        ))
        resp = client.get(
            f"/api/v1/portal/printer/{other_token}/items/item-001/bundle"
        )
        assert resp.status_code == 404

    def test_importer_token_rejected(self, client, admin_headers, mem_blob_store):
        token = _create_token(client, admin_headers, role="importer")
        _await(_plant_bundle_artifact(
            item_id="item-001", tenant_id="tnt-nakoda-001",
            data=b"PK\x03\x04body", store=mem_blob_store,
        ))
        resp = client.get(f"/api/v1/portal/printer/{token}/items/item-001/bundle")
        assert resp.status_code == 404

    def test_invalid_token_404(self, client, mem_blob_store):
        resp = client.get(
            "/api/v1/portal/printer/not-a-real-token/items/item-001/bundle"
        )
        assert resp.status_code == 404

    def test_download_still_works_after_confirm(self, client, admin_headers, mem_blob_store):
        """Reprints should remain possible — confirm isn't a lock-out."""
        token = _create_token(client, admin_headers, role="printer")
        _await(_plant_bundle_artifact(
            item_id="item-001", tenant_id="tnt-nakoda-001",
            data=b"PK\x03\x04body", store=mem_blob_store,
        ))
        # Confirm first.
        c = client.post(f"/api/v1/portal/printer/{token}/confirm", json={})
        assert c.status_code == 200
        # Download after confirm still succeeds.
        d = client.get(f"/api/v1/portal/printer/{token}/items/item-001/bundle")
        assert d.status_code == 200
        assert d.content == b"PK\x03\x04body"
