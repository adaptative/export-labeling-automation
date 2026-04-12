"""Initial schema v2 — 17 tables + materialized view.

Revision ID: 0001
Revises: None
Create Date: 2026-04-12
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Enums --
    itemstate = postgresql.ENUM(
        "CREATED", "INTAKE_CLASSIFIED", "PARSED", "FUSED",
        "COMPLIANCE_EVAL", "DRAWING_GENERATED", "COMPOSED",
        "VALIDATED", "REVIEWED", "DELIVERED", "HUMAN_BLOCKED", "FAILED",
        name="itemstate", create_type=True,
    )
    itemstate.create(op.get_bind(), checkfirst=True)

    documentclass = postgresql.ENUM(
        "PURCHASE_ORDER", "PROFORMA_INVOICE", "PROTOCOL",
        "WARNING_LABELS", "CHECKLIST", "UNKNOWN",
        name="documentclass", create_type=True,
    )
    documentclass.create(op.get_bind(), checkfirst=True)

    # -- tenants --
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- users --
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="viewer"),
        sa.Column("hashed_password", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )

    # -- importers --
    op.create_table(
        "importers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_importers_tenant_code"),
    )

    # -- importer_profiles --
    op.create_table(
        "importer_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("importer_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("importers.id"), nullable=False, index=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("brand_treatment", postgresql.JSONB(), nullable=True),
        sa.Column("panel_layouts", postgresql.JSONB(), nullable=True),
        sa.Column("handling_symbol_rules", postgresql.JSONB(), nullable=True),
        sa.Column("pi_template_mapping", postgresql.JSONB(), nullable=True),
        sa.Column("logo_asset_hash", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("importer_id", "version", name="uq_importer_profiles_importer_version"),
    )

    # -- orders (NO state column) --
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("importer_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("importers.id"), nullable=False, index=True),
        sa.Column("external_ref", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- order_items --
    op.create_table(
        "order_items",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("item_no", sa.String(50), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="CREATED"),
        sa.Column("state_changed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("rules_snapshot_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Index("ix_order_items_state", "state"),
        sa.Index("ix_order_items_order_item", "order_id", "item_no", unique=True),
    )

    # -- documents --
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("s3_key", sa.String(1024), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- documents_classification --
    op.create_table(
        "documents_classification",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("doc_class", sa.String(50), nullable=False, server_default="UNKNOWN"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("classified_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- compliance_rules --
    op.create_table(
        "compliance_rules",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("rule_code", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("logic", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "rule_code", "version", name="uq_compliance_rules_tenant_code_version"),
    )

    # -- rules_snapshots --
    op.create_table(
        "rules_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("snapshot_data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- warning_labels --
    op.create_table(
        "warning_labels",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("text_en", sa.Text(), nullable=False),
        sa.Column("text_es", sa.Text(), nullable=True),
        sa.Column("text_fr", sa.Text(), nullable=True),
        sa.Column("svg_template", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_warning_labels_tenant_code"),
    )

    # -- artifacts --
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("order_item_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("artifact_type", sa.String(100), nullable=False),
        sa.Column("s3_key", sa.String(1024), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- hitl_threads --
    op.create_table(
        "hitl_threads",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("item_no", sa.String(50), nullable=False),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False, server_default="P2"),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Index("ix_hitl_threads_status", "status"),
    )

    # -- hitl_messages --
    op.create_table(
        "hitl_messages",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("thread_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("hitl_threads.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("sender_type", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- cost_events --
    op.create_table(
        "cost_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("scope", sa.String(50), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("model_id", sa.String(100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Index("ix_cost_events_tenant_scope", "tenant_id", "scope"),
    )

    # -- audit_log --
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=True, index=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Index("ix_audit_log_resource", "resource_type", "resource_id"),
    )

    # -- notifications --
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=True, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("level", sa.String(20), nullable=False, server_default="info"),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- Materialized view: order_state_v --
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS order_state_v AS
        SELECT
            o.id AS order_id,
            o.tenant_id,
            CASE
                WHEN bool_or(oi.state = 'FAILED') THEN 'ATTENTION'
                WHEN bool_and(oi.state = 'DELIVERED') THEN 'DELIVERED'
                WHEN bool_or(oi.state = 'HUMAN_BLOCKED') THEN 'HUMAN_BLOCKED'
                WHEN bool_and(oi.state IN ('REVIEWED', 'DELIVERED')) THEN 'READY_TO_DELIVER'
                WHEN bool_and(oi.state = 'CREATED') THEN 'CREATED'
                ELSE 'IN_PROGRESS'
            END AS computed_state,
            COUNT(oi.id) AS item_count,
            MIN(oi.state_changed_at) AS oldest_state_change,
            MAX(oi.state_changed_at) AS newest_state_change
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.id
        GROUP BY o.id, o.tenant_id
        WITH DATA;
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_order_state_v_order_id
        ON order_state_v (order_id);
    """)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS order_state_v;")
    op.drop_table("notifications")
    op.drop_table("audit_log")
    op.drop_table("cost_events")
    op.drop_table("hitl_messages")
    op.drop_table("hitl_threads")
    op.drop_table("artifacts")
    op.drop_table("warning_labels")
    op.drop_table("rules_snapshots")
    op.drop_table("compliance_rules")
    op.drop_table("documents_classification")
    op.drop_table("documents")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("importer_profiles")
    op.drop_table("importers")
    op.drop_table("users")
    op.drop_table("tenants")
    op.execute("DROP TYPE IF EXISTS itemstate;")
    op.execute("DROP TYPE IF EXISTS documentclass;")
