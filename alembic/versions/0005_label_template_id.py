"""Add label_template_id to item_types.

Revision ID: 0005_label_template_id
Revises: 0004_item_relations
Create Date: 2026-01-07
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_label_template_id"
down_revision = "0004_item_relations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("item_types", sa.Column("label_template_id", sa.Text()))


def downgrade() -> None:
    op.drop_column("item_types", "label_template_id")
