import datetime as dt
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from thingdex.crud import (
    IN_USE_RELATION_TYPES,
    build_props_filter,
    get_descendant_location_ids,
    is_item_in_use,
    resolve_effective_location,
    resolve_item_type,
)
from thingdex.db import SessionLocal
from thingdex.labeling import (
    LabelServiceError,
    build_template_variables,
    fetch_template,
    label_printing_enabled,
    print_label,
    required_template_variables,
)
from thingdex.models import Item, ItemPropHistory, ItemRelation, ItemSnapshot, ItemType, Location
from thingdex.schemas import (
    ItemCreate,
    ItemDetailLocation,
    ItemDetailOut,
    ItemDetailType,
    ItemMove,
    ItemOut,
    ItemPropHistoryOut,
    ItemPropsReplace,
    ItemPropsUpdate,
    ItemRelationCreate,
    ItemRelationOut,
    ItemSnapshotCreate,
    ItemSnapshotOut,
    ItemUpdate,
    SearchRequest,
)
from thingdex.validation import SchemaValidationError, track_history_for, validate_props

router = APIRouter(prefix="/v1/items", tags=["items"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=ItemOut)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)):
    """Create an item and validate its props against the item type schema."""
    item_type = resolve_item_type(db, type_name=payload.type, type_id=payload.type_id)
    if not item_type:
        raise HTTPException(status_code=400, detail="Item type not found")
    if payload.location_id is None:
        raise HTTPException(status_code=400, detail="location_id is required for stored items")
    location = db.get(Location, payload.location_id)
    if not location:
        raise HTTPException(status_code=400, detail="Location not found")
    try:
        props = validate_props(item_type.schema, payload.props, partial=False, apply_defaults=True)
    except SchemaValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors) from exc

    template = None
    if payload.label_print is not None:
        if not label_printing_enabled():
            raise HTTPException(status_code=400, detail="Label printing is disabled")
        if not item_type.label_template_id:
            raise HTTPException(status_code=400, detail="Item type has no label_template_id")
        try:
            template = fetch_template(item_type.label_template_id)
        except LabelServiceError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        required_vars = required_template_variables(template)
        missing = [name for name in required_vars if name not in props]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required template variables in props: {', '.join(missing)}",
            )

    item = Item(
        type_id=item_type.id,
        location_id=payload.location_id,
        status=payload.status or "stored",
        description=payload.description,
        props=props,
    )
    db.add(item)
    if payload.label_print is not None and template is not None:
        variables = build_template_variables(template, props)
        try:
            print_label(
                printer_id=payload.label_print.printer_id,
                template=template.get("template", {}),
                variables=variables,
                return_preview=payload.label_print.return_preview,
            )
        except LabelServiceError as exc:
            db.rollback()
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.commit()
    db.refresh(item)
    return item


@router.get("", response_model=list[ItemOut])
def list_items(
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    in_use: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """List items with optional type/status/in-use filters."""
    query = select(Item)
    if type:
        query = query.join(ItemType, Item.type_id == ItemType.id).where(ItemType.name == type)
    if status:
        query = query.where(Item.status == status)
    if in_use is not None:
        in_use_filter = exists(
            select(ItemRelation.id).where(
                ItemRelation.child_item_id == Item.id,
                ItemRelation.active.is_(True),
                ItemRelation.relation_type.in_(IN_USE_RELATION_TYPES),
            )
        )
        query = query.where(in_use_filter if in_use else ~in_use_filter)
    return db.execute(query).scalars().all()


@router.get("/{item_id}", response_model=ItemDetailOut)
def get_item(item_id: UUID, db: Session = Depends(get_db)):
    """Fetch item details with type info and location path."""
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item_type = db.get(ItemType, item.type_id)
    if not item_type:
        raise HTTPException(status_code=404, detail="Item relations not found")
    effective_location_id, effective_path = resolve_effective_location(db, item)
    return ItemDetailOut(
        id=item.id,
        type_id=item.type_id,
        location_id=item.location_id,
        status=item.status,
        description=item.description,
        props=item.props,
        type=ItemDetailType(id=item_type.id, name=item_type.name),
        location=ItemDetailLocation(
            physical_location_id=item.location_id,
            effective_location_id=effective_location_id,
            effective_location_path=effective_path,
        ),
    )


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(item_id: UUID, payload: ItemUpdate, db: Session = Depends(get_db)):
    """Update item metadata (status/description)."""
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if payload.status is not None:
        item.status = payload.status
    if payload.description is not None:
        item.description = payload.description
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{item_id}/move", response_model=ItemOut)
def move_item(item_id: UUID, payload: ItemMove, db: Session = Depends(get_db)):
    """Move an item to a new location ID."""
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if is_item_in_use(db, item_id):
        raise HTTPException(status_code=409, detail="Item is installed or in use")
    location = db.get(Location, payload.location_id)
    if not location:
        raise HTTPException(status_code=400, detail="Location not found")
    item.location_id = payload.location_id
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{item_id}/props", response_model=ItemOut)
def merge_props(item_id: UUID, payload: ItemPropsUpdate, db: Session = Depends(get_db)):
    """Merge props into the item and append history for tracked fields."""
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item_type = db.get(ItemType, item.type_id)
    if not item_type:
        raise HTTPException(status_code=404, detail="Item type not found")

    try:
        updates = validate_props(item_type.schema, payload.props, partial=True)
    except SchemaValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors) from exc

    current_props = dict(item.props or {})
    for key, value in updates.items():
        if current_props.get(key) != value:
            if track_history_for(item_type.schema, key):
                history = ItemPropHistory(
                    item_id=item.id,
                    prop_key=key,
                    value=value,
                    source=payload.source,
                )
                db.add(history)
            current_props[key] = value
    item.props = current_props
    db.commit()
    db.refresh(item)
    return item


@router.put("/{item_id}/props", response_model=ItemOut)
def replace_props(item_id: UUID, payload: ItemPropsReplace, db: Session = Depends(get_db)):
    """Replace the full props object, applying defaults and history."""
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item_type = db.get(ItemType, item.type_id)
    if not item_type:
        raise HTTPException(status_code=404, detail="Item type not found")

    try:
        new_props = validate_props(item_type.schema, payload.props, partial=False, apply_defaults=True)
    except SchemaValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors) from exc

    current_props = dict(item.props or {})
    for key, value in new_props.items():
        if current_props.get(key) != value and track_history_for(item_type.schema, key):
            history = ItemPropHistory(
                item_id=item.id,
                prop_key=key,
                value=value,
                source=payload.source,
            )
            db.add(history)
    item.props = new_props
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/relations", response_model=ItemRelationOut)
def create_relation(item_id: UUID, payload: ItemRelationCreate, db: Session = Depends(get_db)):
    """Attach a child item to a parent item."""
    parent = db.get(Item, item_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent item not found")
    child = db.get(Item, payload.child_item_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child item not found")
    if item_id == payload.child_item_id:
        raise HTTPException(status_code=400, detail="Parent and child cannot be the same item")
    if payload.relation_type in IN_USE_RELATION_TYPES and is_item_in_use(db, payload.child_item_id):
        raise HTTPException(status_code=409, detail="Child item is already in use")

    relation = ItemRelation(
        parent_item_id=item_id,
        child_item_id=payload.child_item_id,
        relation_type=payload.relation_type,
        active=True,
        quantity=payload.quantity,
        slot=payload.slot,
        notes=payload.notes,
    )
    db.add(relation)
    if payload.relation_type in IN_USE_RELATION_TYPES:
        child.location_id = None
    now = dt.datetime.now(dt.timezone.utc)
    parent.updated_at = now
    child.updated_at = now
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Relation already exists") from exc
    db.refresh(relation)
    return relation


@router.get("/{item_id}/relations/children", response_model=list[ItemRelationOut])
def list_child_relations(
    item_id: UUID,
    active_only: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """List relations where this item is the parent."""
    query = db.query(ItemRelation).filter(ItemRelation.parent_item_id == item_id)
    if active_only:
        query = query.filter(ItemRelation.active.is_(True))
    return query.order_by(ItemRelation.created_at.desc()).all()


@router.get("/{item_id}/relations/parents", response_model=list[ItemRelationOut])
def list_parent_relations(
    item_id: UUID,
    active_only: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """List relations where this item is the child."""
    query = db.query(ItemRelation).filter(ItemRelation.child_item_id == item_id)
    if active_only:
        query = query.filter(ItemRelation.active.is_(True))
    return query.order_by(ItemRelation.created_at.desc()).all()


@router.get("/{item_id}/history", response_model=list[ItemPropHistoryOut])
def get_history(
    item_id: UUID,
    prop_key: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Fetch property history for an item."""
    query = db.query(ItemPropHistory).filter(ItemPropHistory.item_id == item_id)
    if prop_key:
        query = query.filter(ItemPropHistory.prop_key == prop_key)
    return query.order_by(ItemPropHistory.captured_at.desc()).limit(limit).all()


@router.post("/{item_id}/snapshots", response_model=ItemSnapshotOut)
def create_snapshot(item_id: UUID, payload: ItemSnapshotCreate, db: Session = Depends(get_db)):
    """Create a snapshot entry (large payloads, tree output, etc.)."""
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    captured_at = None
    if payload.captured_at:
        try:
            captured_at = dt.datetime.fromisoformat(payload.captured_at)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="captured_at must be ISO datetime") from exc
    snapshot = ItemSnapshot(
        item_id=item_id,
        kind=payload.kind,
        captured_at=captured_at,
        data_text=payload.data_text,
        data=payload.data,
        meta=payload.meta or {},
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


@router.get("/{item_id}/snapshots", response_model=list[ItemSnapshotOut])
def list_snapshots(
    item_id: UUID,
    kind: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List snapshots for an item, filtered by kind if provided."""
    query = db.query(ItemSnapshot).filter(ItemSnapshot.item_id == item_id)
    if kind:
        query = query.filter(ItemSnapshot.kind == kind)
    return query.order_by(ItemSnapshot.captured_at.desc()).limit(limit).all()


@router.post("/search", response_model=list[ItemOut])
def search_items(payload: SearchRequest, db: Session = Depends(get_db)):
    """Perform a multi-criteria search across type, location, props, availability."""
    query = select(Item)

    if payload.type:
        query = query.join(ItemType, Item.type_id == ItemType.id).where(ItemType.name == payload.type)

    if payload.location:
        if payload.location.include_descendants:
            location_ids = get_descendant_location_ids(db, payload.location.root_location_id)
            query = query.where(Item.location_id.in_(location_ids))
        else:
            query = query.where(Item.location_id == payload.location.root_location_id)

    if payload.props_filters:
        for prop_filter in payload.props_filters:
            try:
                query = query.where(build_props_filter(prop_filter.path, prop_filter.op, prop_filter.value))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    if payload.in_use is not None:
        in_use_filter = exists(
            select(ItemRelation.id).where(
                ItemRelation.child_item_id == Item.id,
                ItemRelation.active.is_(True),
                ItemRelation.relation_type.in_(IN_USE_RELATION_TYPES),
            )
        )
        query = query.where(in_use_filter if payload.in_use else ~in_use_filter)

    return db.execute(query).scalars().all()
