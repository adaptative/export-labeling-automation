"""Add importer_documents + importer_onboarding_sessions tables.

Supports the Sprint 8 onboarding flow (protocol/warnings/checklist upload,
agent extraction polling, finalize → ImporterProfile).

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-14
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "importer_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("importer_id", sa.String(length=36), sa.ForeignKey("importers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("doc_type", sa.String(length=50), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("s3_key", sa.String(length=1024), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_importer_documents_importer_type",
        "importer_documents",
        ["importer_id", "doc_type"],
    )

    op.create_table(
        "importer_onboarding_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("importer_id", sa.String(length=36), sa.ForeignKey("importers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="in_progress"),
        sa.Column("agents_state", sa.JSON(), nullable=True),
        sa.Column("extracted_values", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_importer_onboarding_importer",
        "importer_onboarding_sessions",
        ["importer_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_importer_onboarding_importer", table_name="importer_onboarding_sessions")
    op.drop_table("importer_onboarding_sessions")
    op.drop_index("ix_importer_documents_importer_type", table_name="importer_documents")
    op.drop_table("importer_documents")
