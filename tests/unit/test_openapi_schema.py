"""Tests for OpenAPI schema type alignment — INT-021."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from labelforge.app import app

client = TestClient(app)


def _get_schema() -> dict:
    resp = client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    return resp.json()


class TestItemStateEnum:
    """Verify ItemState enum has all 12 backend values in the schema."""

    def test_item_state_has_12_values(self):
        schema = _get_schema()
        item_state = schema["components"]["schemas"]["ItemState"]
        assert len(item_state["enum"]) == 12

    def test_item_state_values_match_backend(self):
        schema = _get_schema()
        item_state = schema["components"]["schemas"]["ItemState"]
        expected = [
            "CREATED", "INTAKE_CLASSIFIED", "PARSED", "FUSED",
            "COMPLIANCE_EVAL", "DRAWING_GENERATED", "COMPOSED",
            "VALIDATED", "REVIEWED", "DELIVERED", "HUMAN_BLOCKED", "FAILED",
        ]
        assert sorted(item_state["enum"]) == sorted(expected)


class TestOrderStateEnum:
    def test_order_state_has_6_values(self):
        schema = _get_schema()
        order_state = schema["components"]["schemas"]["OrderState"]
        assert len(order_state["enum"]) == 6


class TestDocumentClassEnum:
    def test_document_class_has_6_values(self):
        schema = _get_schema()
        doc_class = schema["components"]["schemas"]["DocumentClass"]
        assert len(doc_class["enum"]) == 6


class TestContractModels:
    """Verify key contract models appear in the schema."""

    def test_hitl_thread_in_schema(self):
        schema = _get_schema()
        schemas = schema["components"]["schemas"]
        assert "HiTLThread" in schemas
        hitl = schemas["HiTLThread"]
        assert "thread_id" in hitl["properties"]
        assert "priority" in hitl["properties"]
        assert "status" in hitl["properties"]

    def test_importer_profile_in_schema(self):
        schema = _get_schema()
        schemas = schema["components"]["schemas"]
        assert "ImporterProfile" in schemas
        imp = schemas["ImporterProfile"]
        assert "importer_id" in imp["properties"]
        assert "version" in imp["properties"]

    def test_provenance_in_schema(self):
        schema = _get_schema()
        schemas = schema["components"]["schemas"]
        assert "Provenance" in schemas

    def test_order_item_has_state_field(self):
        schema = _get_schema()
        oi = schema["components"]["schemas"]["OrderItem"]
        assert "state" in oi["properties"]

    def test_document_has_doc_class_field(self):
        schema = _get_schema()
        doc = schema["components"]["schemas"]["Document"]
        assert "doc_class" in doc["properties"]


class TestSchemaExamples:
    """Verify json_schema_extra examples are in the schema."""

    def test_hitl_thread_has_example(self):
        schema = _get_schema()
        hitl = schema["components"]["schemas"]["HiTLThread"]
        assert "example" in hitl or "examples" in hitl


class TestSchemaCompleteness:
    """Verify the schema has all expected paths."""

    def test_all_resource_paths_present(self):
        schema = _get_schema()
        paths = set(schema["paths"].keys())
        required = {
            "/api/v1/orders",
            "/api/v1/orders/{order_id}",
            "/api/v1/orders/{order_id}/items",
            "/api/v1/items",
            "/api/v1/items/{item_id}",
            "/api/v1/documents",
            "/api/v1/documents/upload",
            "/api/v1/hitl/threads",
            "/api/v1/hitl/threads/{thread_id}",
            "/api/v1/hitl/threads/{thread_id}/messages",
            "/api/v1/rules",
            "/api/v1/rules/{rule_id}",
            "/api/v1/importers",
            "/api/v1/importers/{importer_id}",
            "/api/v1/artifacts",
            "/api/v1/notifications",
            "/api/v1/warning-labels",
        }
        missing = required - paths
        assert not missing, f"Missing paths: {missing}"

    def test_schema_count(self):
        schema = _get_schema()
        schemas = schema["components"]["schemas"]
        # Should have at least the core contract models
        assert len(schemas) >= 20
