"""Row-Level Security (RLS) policy definitions and helpers.

RLS is enforced at the PostgreSQL level via policies that check:
    tenant_id = current_setting('app.tenant_id')::uuid

The TenantMiddleware (tenant.py) sets ``app.tenant_id`` via SET LOCAL on
every request. If no tenant is set, the empty-string default ensures
fail-closed behavior (no rows returned).

Platform tables (tenants) are exempt from RLS.
"""
from __future__ import annotations

from typing import List

# Tables that have tenant_id and should have RLS enabled
RLS_TABLES: List[str] = [
    "users",
    "importers",
    "importer_profiles",
    "orders",
    "order_items",
    "documents",
    "documents_classification",
    "compliance_rules",
    "rules_snapshots",
    "warning_labels",
    "artifacts",
    "hitl_threads",
    "hitl_messages",
    "cost_events",
    "audit_log",
    "notifications",
]

# Platform tables exempt from RLS
RLS_EXEMPT_TABLES: List[str] = [
    "tenants",
]


def generate_enable_rls_sql(table: str) -> str:
    """Generate SQL to enable RLS on a table."""
    return f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;"


def generate_force_rls_sql(table: str) -> str:
    """Generate SQL to force RLS even for table owners."""
    return f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;"


def generate_policy_sql(table: str) -> str:
    """Generate the tenant isolation policy for a table."""
    return (
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (tenant_id = current_setting('app.tenant_id')::uuid);"
    )


def generate_all_rls_sql() -> str:
    """Generate all RLS SQL statements for all tenant-scoped tables."""
    statements = []
    for table in RLS_TABLES:
        statements.append(generate_enable_rls_sql(table))
        statements.append(generate_force_rls_sql(table))
        statements.append(generate_policy_sql(table))
    return "\n".join(statements)


def generate_disable_rls_sql() -> str:
    """Generate SQL to drop all tenant_isolation policies and disable RLS."""
    statements = []
    for table in RLS_TABLES:
        statements.append(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
        statements.append(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
    return "\n".join(statements)
