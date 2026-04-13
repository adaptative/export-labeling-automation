"""Tests for order creation endpoint — Sprint 5."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from labelforge.app import app


@pytest.fixture(autouse=True)
def _reset_orders():
    """Reset order list between tests."""
    import labelforge.api.v1.orders as orders_mod
    original = list(orders_mod._MOCK_ORDERS)
    yield
    orders_mod._MOCK_ORDERS.clear()
    orders_mod._MOCK_ORDERS.extend(original)


@pytest.fixture
def client():
    return TestClient(app)


class TestCreateOrder:
    def test_create_order_success(self, client, admin_headers):
        resp = client.post(
            "/api/v1/orders",
            json={"importer_id": "IMP-ACME", "po_reference": "PO-99001"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"].startswith("ORD-")
        assert data["importer_id"] == "IMP-ACME"
        assert data["po_number"] == "PO-99001"
        assert data["state"] == "CREATED"
        assert data["item_count"] == 0
        assert "message" in data

    def test_create_order_appears_in_list(self, client, admin_headers):
        create_resp = client.post(
            "/api/v1/orders",
            json={"importer_id": "IMP-GLOBEX"},
            headers=admin_headers,
        )
        order_id = create_resp.json()["id"]

        list_resp = client.get("/api/v1/orders", headers=admin_headers)
        ids = [o["id"] for o in list_resp.json()["orders"]]
        assert order_id in ids

    def test_create_order_without_po_reference(self, client, admin_headers):
        resp = client.post(
            "/api/v1/orders",
            json={"importer_id": "IMP-ACME"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        # po_number should default to order ID
        assert data["po_number"] == data["id"]

    def test_create_order_missing_importer(self, client, admin_headers):
        resp = client.post(
            "/api/v1/orders",
            json={},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_create_order_empty_importer(self, client, admin_headers):
        resp = client.post(
            "/api/v1/orders",
            json={"importer_id": ""},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_create_order_requires_auth(self, client):
        resp = client.post(
            "/api/v1/orders",
            json={"importer_id": "IMP-ACME"},
        )
        assert resp.status_code == 401

    def test_create_order_with_all_fields(self, client, admin_headers):
        resp = client.post(
            "/api/v1/orders",
            json={
                "importer_id": "IMP-ACME",
                "po_reference": "PO-99002",
                "due_date": "2026-05-01",
                "notes": "Rush order",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
