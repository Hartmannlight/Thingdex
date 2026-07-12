"""Enforce inventory tree and active relation invariants.

Revision ID: 0007_inventory_invariants
Revises: 0006_soft_delete
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_inventory_invariants"
down_revision = "0006_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE locations AS orphan
        SET parent_id = root.id
        FROM locations AS root
        WHERE orphan.parent_id IS NULL
          AND orphan.kind IS DISTINCT FROM 'root'
          AND root.parent_id IS NULL
          AND root.kind = 'root'
          AND root.deleted_at IS NULL
        """
    )
    op.create_check_constraint(
        "locations_root_shape_ck",
        "locations",
        "(parent_id IS NULL AND kind = 'root') "
        "OR (parent_id IS NOT NULL AND kind IS DISTINCT FROM 'root')",
    )
    op.create_check_constraint(
        "item_relations_not_self_ck",
        "item_relations",
        "parent_item_id <> child_item_id",
    )
    op.create_check_constraint(
        "item_relations_quantity_positive_ck",
        "item_relations",
        "quantity IS NULL OR quantity > 0",
    )
    op.create_index(
        "item_relations_one_active_in_use_parent",
        "item_relations",
        ["child_item_id"],
        unique=True,
        postgresql_where=sa.text(
            "active = true AND deleted_at IS NULL "
            "AND relation_type IN ('installed_in', 'uses')"
        ),
    )


def downgrade() -> None:
    op.drop_index("item_relations_one_active_in_use_parent", table_name="item_relations")
    op.drop_constraint("item_relations_quantity_positive_ck", "item_relations", type_="check")
    op.drop_constraint("item_relations_not_self_ck", "item_relations", type_="check")
    op.drop_constraint("locations_root_shape_ck", "locations", type_="check")
