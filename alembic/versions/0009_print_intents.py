"""Add transactional PrintHub outbox.

Revision ID: 0009_print_intents
Revises: 0008_label_profiles
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009_print_intents"
down_revision = "0008_label_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "print_intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("entity_kind", sa.Text(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_version", sa.Text(), nullable=False),
        sa.Column("template_id", sa.Text(), nullable=False),
        sa.Column("printer_id", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.Text(), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("printhub_job_id", sa.Text(), nullable=True),
        sa.Column("printhub_job_state", sa.Text(), nullable=True),
        sa.Column("status_sequence", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempts >= 0", name="print_intents_attempts_ck"),
        sa.CheckConstraint(
            "state IN ('pending', 'delivering', 'accepted', 'failed')",
            name="print_intents_state_ck",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "print_intents_due_idx",
        "print_intents",
        ["state", "next_attempt_at", "created_at"],
    )
    op.create_index(
        "print_intents_entity_idx",
        "print_intents",
        ["entity_kind", "entity_id"],
    )
    op.create_table(
        "printhub_status_events",
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("job_state", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["intent_id"], ["print_intents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )


def downgrade() -> None:
    op.drop_table("printhub_status_events")
    op.drop_index("print_intents_entity_idx", table_name="print_intents")
    op.drop_index("print_intents_due_idx", table_name="print_intents")
    op.drop_table("print_intents")
