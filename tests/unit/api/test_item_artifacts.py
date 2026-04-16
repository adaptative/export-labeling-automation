"""Tests for per-item artifact endpoints (INT-006, Sprint-13)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from labelforge.api.v1 import documents as docs_mod
from labelforge.core.blobstore import MemoryBlobStore
from labelforge.db import session as session_mod
from labelforge.db.models import Artifact, AuditLog


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mem_blob_store(monkeypatch):
    """Swap the default filesystem blob store for a clean in-memory one."""
    store = MemoryBlobStore()
    monkeypatch.setattr(docs_mod, "_blob_store", store)
    return store


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


async def _upload_artifact(
    *, item_id: str, tenant_id: str, artifact_type: str,
    data: bytes, mime: str, store: MemoryBlobStore, key: str | None = None,
) -> str:
    """Persist a blob and an Artifact row, return the artifact id."""
    key = key or f"artifacts/{artifact_type}/{uuid4()}"
    meta = await store.upload(key, data, content_type=mime)
    aid = str(uuid4())
    async with session_mod.async_session_factory() as db:
        db.add(Artifact(
            id=aid, tenant_id=tenant_id, order_item_id=item_id,
            artifact_type=artifact_type, s3_key=key,
            content_hash=meta.sha256, size_bytes=len(data),
            mime_type=mime, provenance={},
        ))
        await db.commit()
    return aid


# ── Die-cut SVG ─────────────────────────────────────────────────────────────


class TestDiecutSVG:
    def test_returns_svg_when_artifact_exists(self, client, admin_headers, mem_blob_store):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
        _await(_upload_artifact(
            item_id="item-001", tenant_id="tnt-nakoda-001",
            artifact_type="die_cut_svg", data=svg, mime="image/svg+xml",
            store=mem_blob_store,
        ))
        resp = client.get("/api/v1/items/item-001/diecut-svg", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.content == svg
        assert resp.headers["content-type"].startswith("image/svg+xml")
        assert "X-Content-Hash" in resp.headers

    def test_returns_structured_404_when_no_artifact(self, client, admin_headers, mem_blob_store):
        resp = client.get("/api/v1/items/item-002/diecut-svg", headers=admin_headers)
        assert resp.status_code == 404
        assert resp.json().get("reason") == "not_generated"

    def test_blob_missing_returns_structured_404(self, client, admin_headers, mem_blob_store):
        # Create an artifact row but skip the blob upload.
        async def _plant_row():
            aid = str(uuid4())
            async with session_mod.async_session_factory() as db:
                db.add(Artifact(
                    id=aid, tenant_id="tnt-nakoda-001",
                    order_item_id="item-001",
                    artifact_type="die_cut_svg",
                    s3_key="artifacts/missing.svg",
                    content_hash="sha256:deadbeef",
                    size_bytes=0, mime_type="image/svg+xml",
                    provenance={},
                ))
                await db.commit()
        _await(_plant_row())
        resp = client.get("/api/v1/items/item-001/diecut-svg", headers=admin_headers)
        assert resp.status_code == 404
        assert resp.json().get("reason") == "blob_missing"

    def test_tenant_scoping(self, client, mem_blob_store):
        """Item from another tenant → 404."""
        from labelforge.api.v1.auth import _make_stub_jwt
        other = _make_stub_jwt("u", "other-tenant", "ADMIN", "x@y")
        resp = client.get(
            "/api/v1/items/item-001/diecut-svg",
            headers={"Authorization": f"Bearer {other}"},
        )
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/items/item-001/diecut-svg")
        assert resp.status_code == 401


# ── Approval PDF & bundle ───────────────────────────────────────────────────


class TestApprovalPDF:
    def test_returns_pdf_when_artifact_exists(self, client, admin_headers, mem_blob_store):
        pdf = b"%PDF-1.4\n% fake"
        _await(_upload_artifact(
            item_id="item-001", tenant_id="tnt-nakoda-001",
            artifact_type="approval_pdf", data=pdf,
            mime="application/pdf", store=mem_blob_store,
        ))
        resp = client.get("/api/v1/items/item-001/approval-pdf", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/pdf")
        assert resp.content == pdf

    def test_missing_returns_not_generated(self, client, admin_headers, mem_blob_store):
        resp = client.get("/api/v1/items/item-005/approval-pdf", headers=admin_headers)
        assert resp.status_code == 404
        assert resp.json()["reason"] == "not_generated"


class TestBundle:
    def test_streams_zip_bytes(self, client, admin_headers, mem_blob_store):
        zip_body = b"PK\x03\x04" + b"fake-bundle-body"
        _await(_upload_artifact(
            item_id="item-001", tenant_id="tnt-nakoda-001",
            artifact_type="bundle_zip", data=zip_body,
            mime="application/zip", store=mem_blob_store,
        ))
        resp = client.get("/api/v1/items/item-001/bundle", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.content == zip_body
        assert resp.headers["content-type"].startswith("application/zip")


# ── Line drawing ────────────────────────────────────────────────────────────


class TestLineDrawing:
    def test_prefers_hitl_drawing_over_generated(self, client, admin_headers, mem_blob_store):
        hitl = b'<svg data-source="hitl"/>'
        gen = b'<svg data-source="generated"/>'
        _await(_upload_artifact(
            item_id="item-001", tenant_id="tnt-nakoda-001",
            artifact_type="line_drawing", data=gen, mime="image/svg+xml",
            store=mem_blob_store,
        ))
        _await(_upload_artifact(
            item_id="item-001", tenant_id="tnt-nakoda-001",
            artifact_type="hitl_drawing", data=hitl, mime="image/svg+xml",
            store=mem_blob_store,
        ))
        resp = client.get("/api/v1/items/item-001/line-drawing", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.content == hitl

    def test_falls_back_to_generated_line_drawing(self, client, admin_headers, mem_blob_store):
        gen = b'<svg data-source="generated"/>'
        _await(_upload_artifact(
            item_id="item-002", tenant_id="tnt-nakoda-001",
            artifact_type="line_drawing", data=gen, mime="image/svg+xml",
            store=mem_blob_store,
        ))
        resp = client.get("/api/v1/items/item-002/line-drawing", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.content == gen

    def test_missing_returns_404(self, client, admin_headers, mem_blob_store):
        resp = client.get("/api/v1/items/item-005/line-drawing", headers=admin_headers)
        assert resp.status_code == 404
        assert resp.json()["reason"] == "not_generated"


# ── History ─────────────────────────────────────────────────────────────────


class TestHistory:
    def test_returns_synthetic_entries_for_clean_item(self, client, admin_headers, mem_blob_store):
        resp = client.get("/api/v1/items/item-001/history", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["item_id"] == "item-001"
        assert data["item_no"] == "A1001"
        assert data["current_state"] == "COMPLIANCE_EVAL"
        # At minimum: "item_created" + a final "state_changed" synthetic entry.
        assert len(data["events"]) >= 2
        assert data["events"][0]["action"] == "item_created"
        assert data["events"][-1]["to_state"] == "COMPLIANCE_EVAL"

    def test_includes_audit_entries_in_order(self, client, admin_headers, mem_blob_store):
        async def _plant():
            async with session_mod.async_session_factory() as db:
                db.add(AuditLog(
                    id=str(uuid4()), tenant_id="tnt-nakoda-001",
                    actor="compliance-agent", actor_type="agent",
                    action="state_changed", resource_type="order_item",
                    resource_id="item-001",
                    detail="Moved to COMPLIANCE_EVAL",
                    details={"from_state": "FUSED", "to_state": "COMPLIANCE_EVAL"},
                ))
                await db.commit()
        _await(_plant())
        resp = client.get("/api/v1/items/item-001/history", headers=admin_headers)
        assert resp.status_code == 200
        actions = [e["action"] for e in resp.json()["events"]]
        assert "item_created" in actions
        assert "state_changed" in actions

    def test_not_found_returns_404(self, client, admin_headers, mem_blob_store):
        resp = client.get("/api/v1/items/nonexistent/history", headers=admin_headers)
        assert resp.status_code == 404

    def test_tenant_scoping(self, client, mem_blob_store):
        from labelforge.api.v1.auth import _make_stub_jwt
        other = _make_stub_jwt("u", "other-tenant", "ADMIN", "x@y")
        resp = client.get(
            "/api/v1/items/item-001/history",
            headers={"Authorization": f"Bearer {other}"},
        )
        assert resp.status_code == 404
