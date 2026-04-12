"""Tests for RLS policy definitions — TASK-003."""
from __future__ import annotations

import pytest

from labelforge.core.rls import (
    RLS_TABLES,
    RLS_EXEMPT_TABLES,
    generate_enable_rls_sql,
    generate_force_rls_sql,
    generate_policy_sql,
    generate_all_rls_sql,
    generate_disable_rls_sql,
)


class TestRLSTableLists:
    def test_at_least_12_rls_tables(self):
        assert len(RLS_TABLES) >= 12

    def test_all_expected_tables_covered(self):
        expected = {
            "users", "importers", "importer_profiles", "orders", "order_items",
            "documents", "documents_classification", "compliance_rules",
            "rules_snapshots", "warning_labels", "artifacts",
            "hitl_threads", "hitl_messages", "cost_events",
            "audit_log", "notifications",
        }
        actual = set(RLS_TABLES)
        missing = expected - actual
        assert not missing, f"Missing RLS tables: {missing}"

    def test_tenants_is_exempt(self):
        assert "tenants" in RLS_EXEMPT_TABLES
        assert "tenants" not in RLS_TABLES

    def test_no_overlap_between_rls_and_exempt(self):
        overlap = set(RLS_TABLES) & set(RLS_EXEMPT_TABLES)
        assert not overlap, f"Tables in both lists: {overlap}"


class TestSQLGeneration:
    def test_enable_rls_sql(self):
        sql = generate_enable_rls_sql("orders")
        assert sql == "ALTER TABLE orders ENABLE ROW LEVEL SECURITY;"

    def test_force_rls_sql(self):
        sql = generate_force_rls_sql("orders")
        assert sql == "ALTER TABLE orders FORCE ROW LEVEL SECURITY;"

    def test_policy_sql(self):
        sql = generate_policy_sql("orders")
        assert "tenant_isolation" in sql
        assert "orders" in sql
        assert "current_setting('app.tenant_id')" in sql
        assert "::uuid" in sql

    def test_policy_uses_tenant_id_column(self):
        sql = generate_policy_sql("users")
        assert "tenant_id = current_setting" in sql

    @pytest.mark.parametrize("table", RLS_TABLES)
    def test_each_table_generates_valid_sql(self, table: str):
        enable = generate_enable_rls_sql(table)
        force = generate_force_rls_sql(table)
        policy = generate_policy_sql(table)
        assert table in enable
        assert table in force
        assert table in policy


class TestBulkSQLGeneration:
    def test_generate_all_rls_sql_covers_all_tables(self):
        sql = generate_all_rls_sql()
        for table in RLS_TABLES:
            assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in sql
            assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" in sql
            assert f"CREATE POLICY tenant_isolation ON {table}" in sql

    def test_generate_all_rls_sql_has_correct_count(self):
        sql = generate_all_rls_sql()
        lines = [l for l in sql.strip().split("\n") if l.strip()]
        # 3 statements per table
        assert len(lines) == len(RLS_TABLES) * 3

    def test_generate_disable_rls_sql(self):
        sql = generate_disable_rls_sql()
        for table in RLS_TABLES:
            assert f"DROP POLICY IF EXISTS tenant_isolation ON {table};" in sql
            assert f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;" in sql


class TestMigrationFile:
    def test_migration_0002_exists(self):
        from pathlib import Path
        migration_dir = Path(__file__).parent.parent.parent.parent / "alembic" / "versions"
        files = list(migration_dir.glob("0002_*.py"))
        assert len(files) == 1

    def test_migration_0002_has_rls_content(self):
        from pathlib import Path
        migration = Path(__file__).parent.parent.parent.parent / "alembic" / "versions" / "0002_rls_policies.py"
        content = migration.read_text()
        assert "ENABLE ROW LEVEL SECURITY" in content
        assert "FORCE ROW LEVEL SECURITY" in content
        assert "tenant_isolation" in content
        assert "def upgrade()" in content
        assert "def downgrade()" in content

    def test_migration_0002_depends_on_0001(self):
        from pathlib import Path
        migration = Path(__file__).parent.parent.parent.parent / "alembic" / "versions" / "0002_rls_policies.py"
        content = migration.read_text()
        assert 'down_revision' in content
        assert '"0001"' in content
