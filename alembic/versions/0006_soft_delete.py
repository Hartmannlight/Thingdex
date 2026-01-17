"""Add soft-delete timestamps.

Revision ID: 0006_soft_delete
Revises: 0005_label_template_id
Create Date: 2026-01-08
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_soft_delete"
down_revision = "0005_label_template_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("locations", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column("item_types", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column("items", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column("item_relations", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column("item_prop_history", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column("item_snapshots", sa.Column("deleted_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("item_snapshots", "deleted_at")
    op.drop_column("item_prop_history", "deleted_at")
    op.drop_column("item_relations", "deleted_at")
    op.drop_column("items", "deleted_at")
    op.drop_column("item_types", "deleted_at")
    op.drop_column("locations", "deleted_at")
