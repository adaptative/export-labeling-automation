"""Tests for database models and schema — TASK-002."""
from __future__ import annotations

import pytest
from sqlalchemy import inspect

from labelforge.db.base import Base
from labelforge.db.models import (
    Artifact,
    AuditLog,
    ComplianceRule,
    CostEvent,
    Document,
    DocumentClassEnum,
    DocumentClassification,
    HiTLMessageModel,
    HiTLThreadModel,
    Importer,
    ImporterProfileModel,
    ItemStateEnum,
    Notification,
    Order,
    OrderItemModel,
    RulesSnapshot,
    Tenant,
    User,
    WarningLabel,
    ORDER_STATE_V_SQL,
    ORDER_STATE_V_REFRESH_SQL,
    ORDER_STATE_V_DROP_SQL,
)


class TestItemStateEnum:
    """ItemState enum has exactly 12 values."""

    def test_has_12_values(self):
        assert len(ItemStateEnum) == 12

    def test_all_expected_values(self):
        expected = {
            "CREATED", "INTAKE_CLASSIFIED", "PARSED", "FUSED",
            "COMPLIANCE_EVAL", "DRAWING_GENERATED", "COMPOSED",
            "VALIDATED", "REVIEWED", "DELIVERED", "HUMAN_BLOCKED", "FAILED",
        }
        actual = {e.value for e in ItemStateEnum}
        assert actual == expected

    def test_enum_is_str(self):
        assert isinstance(ItemStateEnum.CREATED, str)
        assert ItemStateEnum.CREATED == "CREATED"


class TestDocumentClassEnum:
    def test_has_6_values(self):
        assert len(DocumentClassEnum) == 6

    def test_values(self):
        expected = {
            "PURCHASE_ORDER", "PROFORMA_INVOICE", "PROTOCOL",
            "WARNING_LABELS", "CHECKLIST", "UNKNOWN",
        }
        assert {e.value for e in DocumentClassEnum} == expected


class TestTableCount:
    """All 17 tables are registered with Base.metadata."""

    def test_at_least_17_tables(self):
        table_names = set(Base.metadata.tables.keys())
        assert len(table_names) >= 17

    def test_all_expected_tables(self):
        expected = {
            "tenants", "users", "importers", "importer_profiles",
            "orders", "order_items", "documents", "documents_classification",
            "compliance_rules", "rules_snapshots", "warning_labels",
            "artifacts", "hitl_threads", "hitl_messages",
            "cost_events", "audit_log", "notifications",
        }
        actual = set(Base.metadata.tables.keys())
        missing = expected - actual
        assert not missing, f"Missing tables: {missing}"


class TestOrdersTableHasNoStateColumn:
    """orders table must NOT have a 'state' column."""

    def test_no_state_column(self):
        orders_table = Base.metadata.tables["orders"]
        column_names = {c.name for c in orders_table.columns}
        assert "state" not in column_names

    def test_has_expected_columns(self):
        orders_table = Base.metadata.tables["orders"]
        column_names = {c.name for c in orders_table.columns}
        required = {"id", "tenant_id", "importer_id", "created_at", "updated_at"}
        missing = required - column_names
        assert not missing, f"Missing columns: {missing}"


class TestOrderItemsTable:
    """order_items has state VARCHAR(32) + state_changed_at."""

    def test_has_state_column(self):
        table = Base.metadata.tables["order_items"]
        col_names = {c.name for c in table.columns}
        assert "state" in col_names
        assert "state_changed_at" in col_names

    def test_state_is_string_type(self):
        table = Base.metadata.tables["order_items"]
        state_col = table.c.state
        assert str(state_col.type) in ("VARCHAR(32)", "String(32)")


class TestArtifactsTable:
    """artifacts has provenance JSONB."""

    def test_has_provenance_jsonb(self):
        table = Base.metadata.tables["artifacts"]
        col_names = {c.name for c in table.columns}
        assert "provenance" in col_names


class TestTenantIdOnTables:
    """Most tables should have a tenant_id FK for RLS readiness."""

    TENANT_TABLES = [
        "users", "importers", "importer_profiles", "orders", "order_items",
        "documents", "documents_classification", "compliance_rules",
        "rules_snapshots", "warning_labels", "artifacts",
        "hitl_threads", "hitl_messages", "cost_events", "audit_log", "notifications",
    ]

    @pytest.mark.parametrize("table_name", TENANT_TABLES)
    def test_has_tenant_id(self, table_name: str):
        table = Base.metadata.tables[table_name]
        col_names = {c.name for c in table.columns}
        assert "tenant_id" in col_names, f"{table_name} missing tenant_id"


class TestIndexes:
    """Verify key indexes exist."""

    def test_order_items_state_index(self):
        table = Base.metadata.tables["order_items"]
        index_names = {idx.name for idx in table.indexes}
        assert "ix_order_items_state" in index_names

    def test_order_items_composite_index(self):
        table = Base.metadata.tables["order_items"]
        index_names = {idx.name for idx in table.indexes}
        assert "ix_order_items_order_item" in index_names

    def test_hitl_threads_status_index(self):
        table = Base.metadata.tables["hitl_threads"]
        index_names = {idx.name for idx in table.indexes}
        assert "ix_hitl_threads_status" in index_names

    def test_cost_events_tenant_scope_index(self):
        table = Base.metadata.tables["cost_events"]
        index_names = {idx.name for idx in table.indexes}
        assert "ix_cost_events_tenant_scope" in index_names

    def test_audit_log_resource_index(self):
        table = Base.metadata.tables["audit_log"]
        index_names = {idx.name for idx in table.indexes}
        assert "ix_audit_log_resource" in index_names


class TestUniqueConstraints:
    def test_users_tenant_email_unique(self):
        table = Base.metadata.tables["users"]
        constraint_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
        assert "uq_users_tenant_email" in constraint_names

    def test_importers_tenant_code_unique(self):
        table = Base.metadata.tables["importers"]
        constraint_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
        assert "uq_importers_tenant_code" in constraint_names

    def test_compliance_rules_version_unique(self):
        table = Base.metadata.tables["compliance_rules"]
        constraint_names = {c.name for c in table.constraints if hasattr(c, "name") and c.name}
        assert "uq_compliance_rules_tenant_code_version" in constraint_names


class TestMaterializedViewSQL:
    """Verify the materialized view SQL strings exist."""

    def test_order_state_v_sql(self):
        assert "order_state_v" in ORDER_STATE_V_SQL
        assert "MATERIALIZED VIEW" in ORDER_STATE_V_SQL
        assert "computed_state" in ORDER_STATE_V_SQL

    def test_refresh_sql(self):
        assert "CONCURRENTLY" in ORDER_STATE_V_REFRESH_SQL

    def test_drop_sql(self):
        assert "DROP MATERIALIZED VIEW" in ORDER_STATE_V_DROP_SQL

    def test_view_derives_all_order_states(self):
        for state in ["ATTENTION", "DELIVERED", "HUMAN_BLOCKED", "READY_TO_DELIVER", "CREATED", "IN_PROGRESS"]:
            assert state in ORDER_STATE_V_SQL, f"Missing state {state} in view SQL"


class TestAlembicMigration:
    """Verify the migration file exists and has correct structure."""

    def test_migration_file_exists(self):
        from pathlib import Path
        migration_dir = Path(__file__).parent.parent.parent / "alembic" / "versions"
        migration_files = list(migration_dir.glob("0001_*.py"))
        assert len(migration_files) == 1

    def test_migration_has_upgrade_and_downgrade(self):
        from pathlib import Path
        migration = Path(__file__).parent.parent.parent / "alembic" / "versions" / "0001_initial_schema.py"
        content = migration.read_text()
        assert "def upgrade()" in content
        assert "def downgrade()" in content
        assert "order_state_v" in content


class TestModelInstantiation:
    """Verify ORM models can be instantiated."""

    def test_tenant(self):
        t = Tenant(id="t1", name="Test Tenant", slug="test")
        assert t.name == "Test Tenant"

    def test_user(self):
        u = User(id="u1", tenant_id="t1", email="a@b.com", display_name="Alice")
        assert u.email == "a@b.com"

    def test_order(self):
        o = Order(id="o1", tenant_id="t1", importer_id="i1")
        assert o.tenant_id == "t1"

    def test_order_item(self):
        oi = OrderItemModel(id="oi1", order_id="o1", tenant_id="t1", item_no="1", state="CREATED")
        assert oi.state == "CREATED"

    def test_document(self):
        d = Document(id="d1", tenant_id="t1", order_id="o1", filename="po.pdf", s3_key="docs/po.pdf")
        assert d.filename == "po.pdf"

    def test_hitl_thread(self):
        t = HiTLThreadModel(id="h1", tenant_id="t1", order_id="o1", item_no="1", agent_id="fusion", priority="P2", status="OPEN")
        assert t.priority == "P2"
        assert t.status == "OPEN"

    def test_artifact(self):
        a = Artifact(id="a1", tenant_id="t1", order_item_id="oi1", artifact_type="die_cut", s3_key="art/a1", content_hash="sha256:abc")
        assert a.artifact_type == "die_cut"

    def test_cost_event(self):
        ce = CostEvent(id="ce1", tenant_id="t1", scope="order", amount_usd=0.05)
        assert ce.amount_usd == 0.05

    def test_audit_log(self):
        al = AuditLog(id="al1", tenant_id="t1", action="create", resource_type="order")
        assert al.action == "create"

    def test_notification(self):
        n = Notification(id="n1", tenant_id="t1", title="New order", is_read=False)
        assert n.is_read is False
