import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Location(Base):
    __tablename__ = "locations"

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


class Item(Base):
    __tablename__ = "items"

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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    prop_key = Column(Text, nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    value = Column(JSONB, nullable=False)
    source = Column(Text)
    deleted_at = Column(DateTime(timezone=True))


class ItemSnapshot(Base):
    __tablename__ = "item_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    kind = Column(Text, nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    data_text = Column(Text)
    data = Column(JSONB)
    meta = Column(JSONB, nullable=False, server_default="{}")
    deleted_at = Column(DateTime(timezone=True))
