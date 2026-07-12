"""Add optional automatic label profiles.

Revision ID: 0008_label_profiles
Revises: 0007_inventory_invariants
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_label_profiles"
down_revision = "0007_inventory_invariants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "label_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("entity_kind", sa.Text(), nullable=False),
        sa.Column("item_type_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("location_kind", sa.Text(), nullable=True),
        sa.Column("template_id", sa.Text(), nullable=False),
        sa.Column("printer_id", sa.Text(), nullable=False),
        sa.Column("auto_print", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("bindings", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("entity_kind IN ('item', 'location')", name="label_profiles_entity_kind_ck"),
        sa.CheckConstraint(
            "(entity_kind = 'item' AND item_type_id IS NOT NULL AND location_kind IS NULL) OR "
            "(entity_kind = 'location' AND item_type_id IS NULL AND location_kind IS NOT NULL)",
            name="label_profiles_selector_ck",
        ),
        sa.ForeignKeyConstraint(["item_type_id"], ["item_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "label_profiles_item_type_unique_idx",
        "label_profiles",
        ["item_type_id"],
        unique=True,
        postgresql_where=sa.text("entity_kind = 'item'"),
    )
    op.create_index(
        "label_profiles_location_kind_unique_idx",
        "label_profiles",
        ["location_kind"],
        unique=True,
        postgresql_where=sa.text("entity_kind = 'location'"),
    )


def downgrade() -> None:
    op.drop_index("label_profiles_location_kind_unique_idx", table_name="label_profiles")
    op.drop_index("label_profiles_item_type_unique_idx", table_name="label_profiles")
    op.drop_table("label_profiles")
