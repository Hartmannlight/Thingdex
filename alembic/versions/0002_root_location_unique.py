"""Ensure unique root location.

Revision ID: 0002_root_location_unique
Revises: 0001_initial
Create Date: 2026-01-07
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_root_location_unique"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE locations
        SET meta = jsonb_set(meta, '{is_root}', 'true'::jsonb, true)
        WHERE kind = 'root' AND parent_id IS NULL
        """
    )
    op.create_index(
        "locations_unique_root_idx",
        "locations",
        ["kind"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NULL AND kind = 'root'"),
    )


def downgrade() -> None:
    op.drop_index("locations_unique_root_idx", table_name="locations")
