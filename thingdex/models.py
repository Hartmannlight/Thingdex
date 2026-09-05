import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint(
            "(parent_id IS NULL AND kind = 'root') "
            "OR (parent_id IS NOT NULL AND kind IS DISTINCT FROM 'root')",
            name="locations_root_shape_ck",
        ),
        Index(
            "locations_unique_root_idx",
            "kind",
            unique=True,
            postgresql_where=text("parent_id IS NULL AND kind = 'root'"),
        ),
        Index("locations_parent_idx", "parent_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"))
    kind = Column(Text)
    meta = Column(JSONB, nullable=False, server_default="{}")
    deleted_at = Column(DateTime(timezone=True))


class ItemType(Base):
    __tablename__ = "item_types"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False, unique=True)
    schema = Column(JSONB, nullable=False, server_default="{}")
    ui = Column(JSONB, nullable=False, server_default="{}")
    label_template_id = Column(Text)
    deleted_at = Column(DateTime(timezone=True))


class LabelProfile(Base):
    __tablename__ = "label_profiles"
    __table_args__ = (
        CheckConstraint("entity_kind IN ('item', 'location')", name="label_profiles_entity_kind_ck"),
        CheckConstraint(
            "(entity_kind = 'item' AND item_type_id IS NOT NULL AND location_kind IS NULL) OR "
            "(entity_kind = 'location' AND item_type_id IS NULL AND location_kind IS NOT NULL)",
            name="label_profiles_selector_ck",
        ),
        Index(
            "label_profiles_item_type_unique_idx",
            "item_type_id",
            unique=True,
            postgresql_where=text("entity_kind = 'item'"),
        ),
        Index(
            "label_profiles_location_kind_unique_idx",
            "location_kind",
            unique=True,
            postgresql_where=text("entity_kind = 'location'"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    entity_kind = Column(Text, nullable=False)
    item_type_id = Column(UUID(as_uuid=True), ForeignKey("item_types.id", ondelete="CASCADE"))
    location_kind = Column(Text)
    template_id = Column(Text, nullable=False)
    printer_id = Column(Text, nullable=False)
    auto_print = Column(Boolean, nullable=False, server_default="true")
    bindings = Column(JSONB, nullable=False, server_default="{}")
    enabled = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class PrintIntent(Base):
    __tablename__ = "print_intents"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending', 'delivering', 'accepted', 'failed')",
            name="print_intents_state_ck",
        ),
        CheckConstraint("attempts >= 0", name="print_intents_attempts_ck"),
        Index("print_intents_due_idx", "state", "next_attempt_at", "created_at"),
        Index("print_intents_entity_idx", "entity_kind", "entity_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key = Column(Text, nullable=False, unique=True)
    entity_kind = Column(Text, nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    entity_version = Column(Text, nullable=False)
    template_id = Column(Text, nullable=False)
    printer_id = Column(Text, nullable=False)
    variables = Column(JSONB, nullable=False)
    state = Column(Text, nullable=False, server_default="pending")
    attempts = Column(Integer, nullable=False, server_default="0")
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text)
    printhub_job_id = Column(Text)
    printhub_job_state = Column(Text)
    status_sequence = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    accepted_at = Column(DateTime(timezone=True))


class PrintHubStatusEvent(Base):
    __tablename__ = "printhub_status_events"

    event_id = Column(Text, primary_key=True)
    intent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("print_intents.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence = Column(Integer, nullable=False)
    job_id = Column(Text, nullable=False)
    job_state = Column(Text, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JSONB, nullable=False)
    applied = Column(Boolean, nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        Index("items_type_idx", "type_id"),
        Index("items_location_idx", "location_id"),
        Index("items_props_gin_idx", "props", postgresql_using="gin"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type_id = Column(UUID(as_uuid=True), ForeignKey("item_types.id", ondelete="RESTRICT"), nullable=False)
    location_id = Column(UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"))
    status = Column(Text, nullable=False, server_default="stored")
    props = Column(JSONB, nullable=False, server_default="{}")
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True))


class ItemRelation(Base):
    __tablename__ = "item_relations"
    __table_args__ = (
        CheckConstraint("parent_item_id <> child_item_id", name="item_relations_not_self_ck"),
        CheckConstraint("quantity IS NULL OR quantity > 0", name="item_relations_quantity_positive_ck"),
        Index(
            "item_relations_unique_active",
            "parent_item_id",
            "child_item_id",
            "relation_type",
            unique=True,
            postgresql_where=text("active = true"),
        ),
        Index(
            "item_relations_one_active_in_use_parent",
            "child_item_id",
            unique=True,
            postgresql_where=text(
                "active = true AND deleted_at IS NULL "
                "AND relation_type IN ('installed_in', 'uses')"
            ),
        ),
        Index("item_relations_parent_idx", "parent_item_id"),
        Index("item_relations_child_idx", "child_item_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    child_item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, server_default="true")
    quantity = Column(Integer)
    slot = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at = Column(DateTime(timezone=True))


class ItemPropHistory(Base):
    __tablename__ = "item_prop_history"
    __table_args__ = (
        Index(
            "item_prop_history_item_key_time_idx",
            "item_id",
            "prop_key",
            "captured_at",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    prop_key = Column(Text, nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    value = Column(JSONB, nullable=False)
    source = Column(Text)
    deleted_at = Column(DateTime(timezone=True))


class ItemSnapshot(Base):
    __tablename__ = "item_snapshots"
    __table_args__ = (
        Index(
            "item_snapshots_item_kind_time_idx",
            "item_id",
            "kind",
            "captured_at",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    kind = Column(Text, nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    data_text = Column(Text)
    data = Column(JSONB)
    meta = Column(JSONB, nullable=False, server_default="{}")
    deleted_at = Column(DateTime(timezone=True))
