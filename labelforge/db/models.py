"""SQLAlchemy ORM models for the Labelforge v2 schema.

Tables (17):
  tenants, users, importers, importer_profiles, orders, order_items,
  documents, documents_classification, compliance_rules, rules_snapshots,
  warning_labels, artifacts, hitl_threads, hitl_messages, cost_events,
  audit_log, notifications

NOTE: ``orders`` has **no** ``state`` column — the aggregate order state is
derived via the ``order_state_v`` materialized view.
"""
import enum
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from labelforge.db.base import Base


# ── Enums ────────────────────────────────────────────────────────────────────


class ItemStateEnum(str, enum.Enum):
    CREATED = "CREATED"
    INTAKE_CLASSIFIED = "INTAKE_CLASSIFIED"
    PARSED = "PARSED"
    FUSED = "FUSED"
    COMPLIANCE_EVAL = "COMPLIANCE_EVAL"
    DRAWING_GENERATED = "DRAWING_GENERATED"
    COMPOSED = "COMPOSED"
    VALIDATED = "VALIDATED"
    REVIEWED = "REVIEWED"
    DELIVERED = "DELIVERED"
    HUMAN_BLOCKED = "HUMAN_BLOCKED"
    FAILED = "FAILED"


class DocumentClassEnum(str, enum.Enum):
    PURCHASE_ORDER = "PURCHASE_ORDER"
    PROFORMA_INVOICE = "PROFORMA_INVOICE"
    PROTOCOL = "PROTOCOL"
    WARNING_LABELS = "WARNING_LABELS"
    CHECKLIST = "CHECKLIST"
    UNKNOWN = "UNKNOWN"


item_state_pg = Enum(
    ItemStateEnum,
    name="itemstate",
    create_constraint=True,
    metadata=Base.metadata,
    schema=None,
    values_callable=lambda e: [m.value for m in e],
)

doc_class_pg = Enum(
    DocumentClassEnum,
    name="documentclass",
    create_constraint=True,
    metadata=Base.metadata,
    schema=None,
    values_callable=lambda e: [m.value for m in e],
)


# ── Helper ───────────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid4())


def _utcnow():
    return func.now()


# ── Tenant ───────────────────────────────────────────────────────────────────


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow(), onupdate=_utcnow())


# ── User ─────────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="viewer")
    hashed_password: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow(), onupdate=_utcnow())

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )


# ── Importer ─────────────────────────────────────────────────────────────────


class Importer(Base):
    __tablename__ = "importers"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_importers_tenant_code"),
    )


class ImporterProfileModel(Base):
    __tablename__ = "importer_profiles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    importer_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("importers.id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    brand_treatment: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    panel_layouts: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    handling_symbol_rules: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    pi_template_mapping: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    logo_asset_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())

    __table_args__ = (
        UniqueConstraint("importer_id", "version", name="uq_importer_profiles_importer_version"),
    )


# ── Order (NO state column) ─────────────────────────────────────────────────


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    importer_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("importers.id"), nullable=False, index=True)
    external_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow(), onupdate=_utcnow())

    items: Mapped[List["OrderItemModel"]] = relationship("OrderItemModel", back_populates="order", lazy="selectin")


# ── OrderItem ────────────────────────────────────────────────────────────────


class OrderItemModel(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    item_no: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default=ItemStateEnum.CREATED.value)
    state_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())
    rules_snapshot_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())

    order: Mapped["Order"] = relationship("Order", back_populates="items")

    __table_args__ = (
        Index("ix_order_items_state", "state"),
        Index("ix_order_items_order_item", "order_id", "item_no", unique=True),
    )


# ── Document ─────────────────────────────────────────────────────────────────


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())


class DocumentClassification(Base):
    __tablename__ = "documents_classification"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    doc_class: Mapped[str] = mapped_column(String(50), nullable=False, default=DocumentClassEnum.UNKNOWN.value)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    classified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())


# ── Compliance ───────────────────────────────────────────────────────────────


class ComplianceRule(Base):
    __tablename__ = "compliance_rules"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    rule_code: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logic: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())

    __table_args__ = (
        UniqueConstraint("tenant_id", "rule_code", "version", name="uq_compliance_rules_tenant_code_version"),
    )


class RulesSnapshot(Base):
    __tablename__ = "rules_snapshots"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    snapshot_data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())


# ── Warning Labels ───────────────────────────────────────────────────────────


class WarningLabel(Base):
    __tablename__ = "warning_labels"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    text_en: Mapped[str] = mapped_column(Text, nullable=False)
    text_es: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text_fr: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    svg_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_warning_labels_tenant_code"),
    )


# ── Artifacts ────────────────────────────────────────────────────────────────


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    order_item_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())


# ── HiTL ─────────────────────────────────────────────────────────────────────


class HiTLThreadModel(Base):
    __tablename__ = "hitl_threads"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    item_no: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="P2")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    sla_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[List["HiTLMessageModel"]] = relationship("HiTLMessageModel", back_populates="thread", lazy="selectin")

    __table_args__ = (
        Index("ix_hitl_threads_status", "status"),
    )


class HiTLMessageModel(Base):
    __tablename__ = "hitl_messages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    thread_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("hitl_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())

    thread: Mapped["HiTLThreadModel"] = relationship("HiTLThreadModel", back_populates="messages")


# ── Cost Events ──────────────────────────────────────────────────────────────


class CostEvent(Base):
    __tablename__ = "cost_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(50), nullable=False)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    model_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())

    __table_args__ = (
        Index("ix_cost_events_tenant_scope", "tenant_id", "scope"),
    )


# ── Audit Log ────────────────────────────────────────────────────────────────


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())

    __table_args__ = (
        Index("ix_audit_log_resource", "resource_type", "resource_id"),
    )


# ── Notifications ────────────────────────────────────────────────────────────


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_utcnow())


# ── Materialized view SQL (executed in migration) ────────────────────────────

ORDER_STATE_V_SQL = """
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
"""

ORDER_STATE_V_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS ix_order_state_v_order_id ON order_state_v (order_id);
"""

ORDER_STATE_V_REFRESH_SQL = "REFRESH MATERIALIZED VIEW CONCURRENTLY order_state_v;"

ORDER_STATE_V_DROP_SQL = "DROP MATERIALIZED VIEW IF EXISTS order_state_v;"
