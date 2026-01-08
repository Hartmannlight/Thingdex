"""Add item relations and nullable locations; drop assignments.

Revision ID: 0004_item_relations
Revises: 0003_drop_item_name
Create Date: 2026-01-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_item_relations"
down_revision = "0003_drop_item_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("items", "location_id", nullable=True)

    op.create_table(
        "item_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "parent_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "child_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("quantity", sa.Integer()),
        sa.Column("slot", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("item_relations_parent_idx", "item_relations", ["parent_item_id"])
    op.create_index("item_relations_child_idx", "item_relations", ["child_item_id"])
    op.create_index(
        "item_relations_unique_active",
        "item_relations",
        ["parent_item_id", "child_item_id", "relation_type"],
        unique=True,
        postgresql_where=sa.text("active = true"),
    )

    op.drop_table("assignments")


def downgrade() -> None:
    op.create_table(
        "assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("assignments_item_idx", "assignments", ["item_id"])
    op.create_index("assignments_target_idx", "assignments", ["target_kind", "target_id"])

    op.drop_index("item_relations_unique_active", table_name="item_relations")
    op.drop_index("item_relations_child_idx", table_name="item_relations")
    op.drop_index("item_relations_parent_idx", table_name="item_relations")
    op.drop_table("item_relations")
    op.alter_column("items", "location_id", nullable=False)
