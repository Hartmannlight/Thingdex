"""Drop items.name.

Revision ID: 0003_drop_item_name
Revises: 0002_root_location_unique
Create Date: 2026-01-07
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_drop_item_name"
down_revision = "0002_root_location_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("items", "name")


def downgrade() -> None:
    op.add_column("items", sa.Column("name", sa.Text(), nullable=False, server_default=""))
    op.alter_column("items", "name", server_default=None)
