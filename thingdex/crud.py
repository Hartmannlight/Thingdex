from __future__ import annotations

import datetime as dt
import os
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import Date, DateTime, Numeric, cast, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from thingdex.models import Item, ItemRelation, ItemType, Location

IN_USE_RELATION_TYPES = {"installed_in", "uses"}


def get_location_path(db: Session, location_id: UUID) -> list[dict[str, Any]]:
    base = select(Location.id, Location.name, Location.parent_id).where(
        Location.id == location_id,
        Location.deleted_at.is_(None),
    )
    cte = base.cte(recursive=True)
    parent = select(Location.id, Location.name, Location.parent_id).where(
        Location.id == cte.c.parent_id,
        Location.deleted_at.is_(None),
    )
    cte = cte.union_all(parent)

    rows = db.execute(select(cte.c.id, cte.c.name, cte.c.parent_id)).all()
    path = [{"id": row.id, "name": row.name} for row in rows]
    path.reverse()
    return path


def get_descendant_location_ids(
    db: Session,
    root_location_id: UUID,
    *,
    include_deleted: bool = False,
) -> list[UUID]:
    base_filters = [Location.id == root_location_id]
    if not include_deleted:
        base_filters.append(Location.deleted_at.is_(None))
    base = select(Location.id).where(*base_filters)
    cte = base.cte(recursive=True)
    recursive_filters = [Location.parent_id == cte.c.id]
    if not include_deleted:
        recursive_filters.append(Location.deleted_at.is_(None))
    cte = cte.union_all(select(Location.id).where(*recursive_filters))
    rows = db.execute(select(cte.c.id)).scalars().all()
    return rows


def resolve_item_type(db: Session, *, type_name: str | None, type_id: UUID | None) -> ItemType | None:
    if type_id is not None:
        return db.execute(
            select(ItemType).where(ItemType.id == type_id, ItemType.deleted_at.is_(None))
        ).scalars().first()
    if type_name is None:
        return None
    return (
        db.execute(select(ItemType).where(ItemType.name == type_name, ItemType.deleted_at.is_(None)))
        .scalars()
        .first()
    )


def get_root_location(db: Session) -> Location | None:
    return (
        db.query(Location)
        .filter(Location.parent_id.is_(None), Location.kind == "root", Location.deleted_at.is_(None))
        .order_by(Location.name)
        .first()
    )


def ensure_root_location(db: Session, *, name: str | None = None) -> Location:
    if name is None:
        name = os.getenv("ROOT_LOCATION_NAME", "World")
    root = get_root_location(db)
    if root:
        return root
    root = Location(name=name, parent_id=None, kind="root", meta={"is_root": True})
    db.add(root)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        root = get_root_location(db)
        if root:
            return root
        raise
    db.refresh(root)
    return root


def _parse_datetime(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def build_props_filter(prop_path: str, op: str, value: Any):
    column = Item.props[prop_path].astext
    if op == "contains":
        if not isinstance(value, str):
            raise ValueError("contains requires string value")
        return column.ilike(f"%{value}%")

    if op == "in":
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
            raise ValueError("in requires list value")
        values = list(value)
        if not values:
            raise ValueError("in requires non-empty list value")
        sample = values[0]
        if isinstance(sample, (int, float)) and not isinstance(sample, bool):
            return cast(column, Numeric).in_(values)
        return column.in_(values)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        left = cast(column, Numeric)
        right = value
    elif isinstance(value, str):
        parsed_dt = _parse_datetime(value)
        parsed_date = _parse_date(value) if parsed_dt is None else None
        if parsed_dt is not None:
            left = cast(column, DateTime)
            right = parsed_dt
        elif parsed_date is not None:
            left = cast(column, Date)
            right = parsed_date
        else:
            left = column
            right = value
    else:
        left = column
        right = value

    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    raise ValueError(f"unsupported operator '{op}'")


def is_item_in_use(db: Session, item_id: UUID) -> bool:
    return (
        db.execute(
            select(ItemRelation.id).where(
                ItemRelation.child_item_id == item_id,
                ItemRelation.active.is_(True),
                ItemRelation.relation_type.in_(IN_USE_RELATION_TYPES),
                ItemRelation.deleted_at.is_(None),
            )
        )
        .first()
        is not None
    )


def active_parent_relation(db: Session, item_id: UUID) -> ItemRelation | None:
    return (
        db.query(ItemRelation)
        .filter(
            ItemRelation.child_item_id == item_id,
            ItemRelation.active.is_(True),
            ItemRelation.relation_type.in_(IN_USE_RELATION_TYPES),
            ItemRelation.deleted_at.is_(None),
        )
        .order_by(ItemRelation.created_at.desc())
        .first()
    )


def resolve_effective_location(db: Session, item: Item) -> tuple[UUID | None, list[dict[str, Any]] | None]:
    if item.location_id:
        location = db.get(Location, item.location_id)
        if location and location.deleted_at is None:
            return item.location_id, get_location_path(db, item.location_id)
        return None, None

    seen: set[UUID] = set()
    current_id = item.id
    while True:
        if current_id in seen:
            return None, None
        seen.add(current_id)
        relation = active_parent_relation(db, current_id)
        if relation is None:
            return None, None
        parent = db.get(Item, relation.parent_item_id)
        if not parent or parent.deleted_at is not None:
            return None, None
        if parent.location_id:
            location = db.get(Location, parent.location_id)
            if location and location.deleted_at is None:
                return parent.location_id, get_location_path(db, parent.location_id)
        current_id = parent.id
