"""Add approval workflow + compliance metadata columns to warning_labels.

Supports INT-011 (Sprint 10) warning-labels library CRUD: status field
(pending/approved/rejected/deprecated), approval actor/timestamp,
reject reason, physical size, trigger conditions JSON, variants JSON,
and the creator id for audit.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-15
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("warning_labels") as batch:
        batch.add_column(
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="approved",
            )
        )
        batch.add_column(sa.Column("size_mm_width", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("size_mm_height", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("trigger_conditions", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("variants", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("created_by", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("approved_by", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("rejected_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("warning_labels") as batch:
        batch.drop_column("rejected_reason")
        batch.drop_column("approved_at")
        batch.drop_column("approved_by")
        batch.drop_column("created_by")
        batch.drop_column("variants")
        batch.drop_column("trigger_conditions")
        batch.drop_column("size_mm_height")
        batch.drop_column("size_mm_width")
        batch.drop_column("status")
