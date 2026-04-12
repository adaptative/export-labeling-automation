"""Tests for all API v1 route endpoints — INT-001."""
from __future__ import annotations

from fastapi.testclient import TestClient

from labelforge.app import app

client = TestClient(app)


# ── Orders ────────────────────────────────────────────────────────────────────


class TestOrders:
    def test_list_orders(self):
        resp = client.get("/api/v1/orders")
        assert resp.status_code == 200
        data = resp.json()
        assert "orders" in data
        assert "total" in data
        assert len(data["orders"]) > 0
        assert "id" in data["orders"][0]

    def test_list_orders_filter_by_state(self):
        resp = client.get("/api/v1/orders", params={"state": "IN_PROGRESS"})
        assert resp.status_code == 200

    def test_get_order(self):
        # Use an ID that the mock data returns
        orders = client.get("/api/v1/orders").json()["orders"]
        order_id = orders[0]["id"]
        resp = client.get(f"/api/v1/orders/{order_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == order_id

    def test_list_order_items(self):
        orders = client.get("/api/v1/orders").json()["orders"]
        order_id = orders[0]["id"]
        resp = client.get(f"/api/v1/orders/{order_id}/items")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ── Items ─────────────────────────────────────────────────────────────────────


class TestItems:
    def test_list_items(self):
        resp = client.get("/api/v1/items")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_item(self):
        items = client.get("/api/v1/items").json()
        item_id = items[0]["id"]
        resp = client.get(f"/api/v1/items/{item_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == item_id


# ── Documents ─────────────────────────────────────────────────────────────────


class TestDocuments:
    def test_list_documents(self):
        resp = client.get("/api/v1/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert "documents" in data
        assert "total" in data

    def test_upload_document(self):
        resp = client.post(
            "/api/v1/documents/upload",
            params={"order_id": "ORD-001"},
            files={"file": ("test-po.pdf", b"fake pdf content", "application/pdf")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["doc_class"] == "PURCHASE_ORDER"


# ── HiTL ──────────────────────────────────────────────────────────────────────


class TestHiTL:
    def test_list_threads(self):
        resp = client.get("/api/v1/hitl/threads")
        assert resp.status_code == 200
        data = resp.json()
        assert "threads" in data
        assert "total" in data

    def test_get_thread(self):
        threads = client.get("/api/v1/hitl/threads").json()["threads"]
        thread_id = threads[0]["thread_id"]
        resp = client.get(f"/api/v1/hitl/threads/{thread_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "thread" in data

    def test_post_message(self):
        threads = client.get("/api/v1/hitl/threads").json()["threads"]
        thread_id = threads[0]["thread_id"]
        resp = client.post(
            f"/api/v1/hitl/threads/{thread_id}/messages",
            json={"sender_type": "human", "content": "Looks correct to me"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "Looks correct to me"


# ── Rules ─────────────────────────────────────────────────────────────────────


class TestRules:
    def test_list_rules(self):
        resp = client.get("/api/v1/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert "rules" in data
        assert "total" in data

    def test_get_rule(self):
        rules = client.get("/api/v1/rules").json()["rules"]
        rule_id = rules[0]["id"]
        resp = client.get(f"/api/v1/rules/{rule_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == rule_id


# ── Importers ─────────────────────────────────────────────────────────────────


class TestImporters:
    def test_list_importers(self):
        resp = client.get("/api/v1/importers")
        assert resp.status_code == 200
        data = resp.json()
        assert "importers" in data
        assert "total" in data

    def test_get_importer(self):
        importers = client.get("/api/v1/importers").json()["importers"]
        importer_id = importers[0]["importer_id"]
        resp = client.get(f"/api/v1/importers/{importer_id}")
        assert resp.status_code == 200


# ── Artifacts ─────────────────────────────────────────────────────────────────


class TestArtifacts:
    def test_list_artifacts(self):
        resp = client.get("/api/v1/artifacts")
        assert resp.status_code == 200
        data = resp.json()
        assert "artifacts" in data
        assert "total" in data


# ── Notifications ─────────────────────────────────────────────────────────────


class TestNotifications:
    def test_list_notifications(self):
        resp = client.get("/api/v1/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert "notifications" in data
        assert "unread_count" in data


# ── Warning Labels ────────────────────────────────────────────────────────────


class TestWarningLabels:
    def test_list_warning_labels(self):
        resp = client.get("/api/v1/warning-labels")
        assert resp.status_code == 200
        data = resp.json()
        assert "warning_labels" in data
        assert "total" in data


# ── OpenAPI Schema ────────────────────────────────────────────────────────────


class TestOpenAPISchema:
    def test_schema_has_all_paths(self):
        resp = client.get("/api/v1/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        paths = list(schema["paths"].keys())
        expected_paths = [
            "/api/v1/orders",
            "/api/v1/orders/{order_id}",
            "/api/v1/items",
            "/api/v1/documents",
            "/api/v1/hitl/threads",
            "/api/v1/rules",
            "/api/v1/importers",
            "/api/v1/artifacts",
            "/api/v1/notifications",
            "/api/v1/warning-labels",
        ]
        for path in expected_paths:
            assert path in paths, f"Missing path: {path}"
