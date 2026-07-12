import datetime as dt
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from thingdex.crud import (
    IN_USE_RELATION_TYPES,
    build_props_filter,
    get_descendant_location_ids,
    is_item_in_use,
    lock_in_use_relation_graph,
    resolve_effective_location,
    resolve_item_type,
    would_create_in_use_cycle,
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
from thingdex.models import Item, ItemPropHistory, ItemRelation, ItemSnapshot, ItemType, LabelProfile, Location
from thingdex.schemas import (
    ItemBulkCreate,
    ItemBulkMove,
    ItemBulkUpdate,
    ItemCreate,
    ItemCreateResponse,
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
    LabelPrintRequest,
    SideEffectResult,
    SideEffects,
)
from thingdex.validation import SchemaValidationError, track_history_for, validate_props

router = APIRouter(prefix="/v1/items", tags=["items"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=ItemCreateResponse)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)):
    """Create an item and validate its props against the item type schema."""
    item_type = resolve_item_type(db, type_name=payload.type, type_id=payload.type_id)
    if not item_type:
        raise HTTPException(status_code=400, detail="Item type not found")
    if payload.location_id is None:
        raise HTTPException(status_code=400, detail="location_id is required for stored items")
    location = db.get(Location, payload.location_id)
    if not location or location.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Location not found")
    try:
        props = validate_props(item_type.schema, payload.props, partial=False, apply_defaults=True)
    except SchemaValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors) from exc

    profile = (
        db.query(LabelProfile)
        .filter(
            LabelProfile.entity_kind == "item",
            LabelProfile.item_type_id == item_type.id,
            LabelProfile.enabled.is_(True),
            LabelProfile.auto_print.is_(True),
        )
        .one_or_none()
    )
    label_request = payload.label_print
    profile_bindings: dict[str, str] = {}
    if label_request is None and profile is not None:
        label_request = LabelPrintRequest(
            printer_id=profile.printer_id,
            template_id=profile.template_id,
        )
        profile_bindings = dict(profile.bindings or {})

    label_print_result = None
    if label_request is not None:
        label_print_result = SideEffectResult(requested=True, success=False)

    item = Item(
        type_id=item_type.id,
        location_id=payload.location_id,
        status=payload.status or "stored",
        description=payload.description,
        props=props,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    if label_request is not None and label_print_result is not None:
        template_id = label_request.template_id or item_type.label_template_id
        if not label_printing_enabled():
            label_print_result.error = "Label printing is disabled"
        if not label_print_result.error and not template_id:
            label_print_result.error = "Item type has no label_template_id"
        elif not label_print_result.error:
            try:
                template = fetch_template(template_id)
                variables = build_template_variables(
                    template,
                    props,
                    context={
                        "entity": {
                            "id": str(item.id),
                            "display_name": item.description or item_type.name,
                            "description": item.description or "",
                            "status": item.status,
                        },
                        "item": {"id": str(item.id), "type": item_type.name},
                        "location": {"id": str(location.id), "name": location.name},
                    },
                    bindings=profile_bindings,
                )
                required_vars = [name for name in required_template_variables(template) if name != "internal_uuid"]
                missing = [name for name in required_vars if name not in variables]
                if missing:
                    label_print_result.error = (
                        "Missing required template variables: "
                        f"{', '.join(missing)}"
                    )
                    return ItemCreateResponse(
                        data=item,
                        side_effects=SideEffects(label_print=label_print_result),
                    )
                variables["internal_uuid"] = str(item.id)
                print_response = print_label(
                    printer_id=label_request.printer_id,
                    template=template.get("template", {}),
                    variables=variables,
                    return_preview=label_request.return_preview,
                    template_id=template_id,
                    idempotency_key=f"thingdex:item:{item.id}:create",
                    origin="thingdex",
                )
                label_print_result.success = True
                label_print_result.result = print_response
            except LabelServiceError as exc:
                label_print_result.error = str(exc)
    return ItemCreateResponse(
        data=item,
        side_effects=SideEffects(label_print=label_print_result),
    )


@router.post("/bulk", response_model=list[ItemOut])
def bulk_create_items(payload: ItemBulkCreate, db: Session = Depends(get_db)):
    """Create multiple items in a single request."""
    if not payload.items:
        return []
    items: list[Item] = []
    errors: list[dict[str, object]] = []
    for index, entry in enumerate(payload.items):
        entry_errors: list[str] = []
        item_type = resolve_item_type(db, type_name=entry.type, type_id=entry.type_id)
        if not item_type:
            entry_errors.append("Item type not found")
        if entry.location_id is None:
            entry_errors.append("location_id is required for stored items")
        else:
            location = db.get(Location, entry.location_id)
            if not location or location.deleted_at is not None:
                entry_errors.append("Location not found")
        props: dict[str, object] | None = None
        if not entry_errors:
            try:
                props = validate_props(item_type.schema, entry.props, partial=False, apply_defaults=True)
            except SchemaValidationError as exc:
                entry_errors.extend(exc.errors)
        if entry_errors:
            errors.append({"index": index, "detail": entry_errors})
            continue
        item = Item(
            type_id=item_type.id,
            location_id=entry.location_id,
            status=entry.status or "stored",
            description=entry.description,
            props=props or {},
        )
        db.add(item)
        items.append(item)
    if errors:
        db.rollback()
        raise HTTPException(status_code=400, detail={"errors": errors})
    db.commit()
    for item in items:
        db.refresh(item)
    return items


@router.patch("/bulk", response_model=list[ItemOut])
def bulk_update_items(payload: ItemBulkUpdate, db: Session = Depends(get_db)):
    """Update multiple items (status/description/props) in a single request."""
    if not payload.items:
        return []
    items: list[Item] = []
    errors: list[dict[str, object]] = []
    for index, entry in enumerate(payload.items):
        entry_errors: list[str] = []
        item = db.get(Item, entry.id)
        if not item or item.deleted_at is not None:
            entry_errors.append("Item not found")
        if item and item.deleted_at is None:
            if entry.status is not None:
                item.status = entry.status
            if entry.description is not None:
                item.description = entry.description
            if entry.props is not None:
                item_type = db.get(ItemType, item.type_id)
                if not item_type or item_type.deleted_at is not None:
                    entry_errors.append("Item type not found")
                else:
                    try:
                        updates = validate_props(item_type.schema, entry.props, partial=True)
                    except SchemaValidationError as exc:
                        entry_errors.extend(exc.errors)
                    else:
                        current_props = dict(item.props or {})
                        for key, value in updates.items():
                            if current_props.get(key) != value:
                                if track_history_for(item_type.schema, key):
                                    history = ItemPropHistory(
                                        item_id=item.id,
                                        prop_key=key,
                                        value=value,
                                        source=entry.source,
                                    )
                                    db.add(history)
                                current_props[key] = value
                        item.props = current_props
        if entry_errors:
            errors.append({"index": index, "id": str(entry.id), "detail": entry_errors})
            continue
        if item:
            items.append(item)
    if errors:
        db.rollback()
        raise HTTPException(status_code=400, detail={"errors": errors})
    db.commit()
    for item in items:
        db.refresh(item)
    return items


@router.patch("/bulk/move", response_model=list[ItemOut])
def bulk_move_items(payload: ItemBulkMove, db: Session = Depends(get_db)):
    """Move multiple items to a new location ID."""
    if not payload.item_ids:
        return []
    location = db.get(Location, payload.location_id)
    if not location or location.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Location not found")
    items: list[Item] = []
    errors: list[dict[str, object]] = []
    for index, item_id in enumerate(payload.item_ids):
        entry_errors: list[str] = []
        item = db.get(Item, item_id)
        if not item or item.deleted_at is not None:
            entry_errors.append("Item not found")
        elif is_item_in_use(db, item_id):
            entry_errors.append("Item is installed or in use")
        if entry_errors:
            errors.append({"index": index, "id": str(item_id), "detail": entry_errors})
            continue
        item.location_id = payload.location_id
        items.append(item)
    if errors:
        db.rollback()
        raise HTTPException(status_code=400, detail={"errors": errors})
    db.commit()
    for item in items:
        db.refresh(item)
    return items


@router.get("", response_model=list[ItemOut])
def list_items(
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    in_use: bool | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """List items with optional type/status/in-use filters."""
    query = select(Item)
    if not include_deleted:
        query = query.where(Item.deleted_at.is_(None))
    if type:
        query = query.join(ItemType, Item.type_id == ItemType.id).where(
            ItemType.name == type,
            ItemType.deleted_at.is_(None),
        )
    if status:
        query = query.where(Item.status == status)
    if in_use is not None:
        in_use_filter = exists(
            select(ItemRelation.id).where(
                ItemRelation.child_item_id == Item.id,
                ItemRelation.active.is_(True),
                ItemRelation.relation_type.in_(IN_USE_RELATION_TYPES),
                ItemRelation.deleted_at.is_(None),
            )
        )
        query = query.where(in_use_filter if in_use else ~in_use_filter)
    query = query.order_by(Item.created_at.desc())
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return db.execute(query).scalars().all()


@router.get("/missing-location", response_model=list[ItemDetailOut])
def list_items_missing_location(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """List items without an effective location."""
    query = db.query(Item).filter(Item.location_id.is_(None))
    if not include_deleted:
        query = query.filter(Item.deleted_at.is_(None))
    items = query.order_by(Item.created_at.desc()).all()

    results: list[ItemDetailOut] = []
    seen = 0
    for item in items:
        item_type = db.get(ItemType, item.type_id)
        if not item_type or item_type.deleted_at is not None:
            continue
        effective_location_id, effective_path = resolve_effective_location(db, item)
        if effective_location_id is not None:
            continue
        if seen < offset:
            seen += 1
            continue
        results.append(
            ItemDetailOut(
                id=item.id,
                type_id=item.type_id,
                location_id=item.location_id,
                status=item.status,
                description=item.description,
                props=item.props,
                type=ItemDetailType(id=item_type.id, name=item_type.name),
                location=ItemDetailLocation(
                    physical_location_id=item.location_id,
                    effective_location_id=None,
                    effective_location_path=effective_path,
                ),
            )
        )
        seen += 1
        if len(results) >= limit:
            break
    return results


@router.get("/{item_id}", response_model=ItemDetailOut)
def get_item(item_id: UUID, db: Session = Depends(get_db)):
    """Fetch item details with type info and location path."""
    item = db.get(Item, item_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")
    item_type = db.get(ItemType, item.type_id)
    if not item_type or item_type.deleted_at is not None:
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
    if not item or item.deleted_at is not None:
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
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")
    if is_item_in_use(db, item_id):
        raise HTTPException(status_code=409, detail="Item is installed or in use")
    location = db.get(Location, payload.location_id)
    if not location or location.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Location not found")
    item.location_id = payload.location_id
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{item_id}/props", response_model=ItemOut)
def merge_props(item_id: UUID, payload: ItemPropsUpdate, db: Session = Depends(get_db)):
    """Merge props into the item and append history for tracked fields."""
    item = db.get(Item, item_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")
    item_type = db.get(ItemType, item.type_id)
    if not item_type or item_type.deleted_at is not None:
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
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")
    item_type = db.get(ItemType, item.type_id)
    if not item_type or item_type.deleted_at is not None:
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
    if not parent or parent.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Parent item not found")
    child = db.get(Item, payload.child_item_id)
    if not child or child.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Child item not found")
    if item_id == payload.child_item_id:
        raise HTTPException(status_code=400, detail="Parent and child cannot be the same item")
    if payload.relation_type in IN_USE_RELATION_TYPES:
        lock_in_use_relation_graph(db)
        if is_item_in_use(db, payload.child_item_id):
            raise HTTPException(status_code=409, detail="Child item is already in use")
        if would_create_in_use_cycle(
            db,
            parent_item_id=item_id,
            child_item_id=payload.child_item_id,
        ):
            raise HTTPException(status_code=409, detail="Relation would create an in-use cycle")

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
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """List relations where this item is the parent."""
    item = db.get(Item, item_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")
    query = db.query(ItemRelation).filter(ItemRelation.parent_item_id == item_id)
    if active_only:
        query = query.filter(ItemRelation.active.is_(True))
    if not include_deleted:
        query = query.filter(ItemRelation.deleted_at.is_(None))
    return query.order_by(ItemRelation.created_at.desc()).all()


@router.get("/{item_id}/relations/parents", response_model=list[ItemRelationOut])
def list_parent_relations(
    item_id: UUID,
    active_only: bool = Query(default=True),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """List relations where this item is the child."""
    item = db.get(Item, item_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")
    query = db.query(ItemRelation).filter(ItemRelation.child_item_id == item_id)
    if active_only:
        query = query.filter(ItemRelation.active.is_(True))
    if not include_deleted:
        query = query.filter(ItemRelation.deleted_at.is_(None))
    return query.order_by(ItemRelation.created_at.desc()).all()


@router.get("/{item_id}/history", response_model=list[ItemPropHistoryOut])
def get_history(
    item_id: UUID,
    prop_key: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Fetch property history for an item."""
    item = db.get(Item, item_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")
    query = db.query(ItemPropHistory).filter(ItemPropHistory.item_id == item_id)
    if prop_key:
        query = query.filter(ItemPropHistory.prop_key == prop_key)
    if not include_deleted:
        query = query.filter(ItemPropHistory.deleted_at.is_(None))
    query = query.order_by(ItemPropHistory.captured_at.desc())
    if offset:
        query = query.offset(offset)
    return query.limit(limit).all()


@router.post("/{item_id}/snapshots", response_model=ItemSnapshotOut)
def create_snapshot(item_id: UUID, payload: ItemSnapshotCreate, db: Session = Depends(get_db)):
    """Create a snapshot entry (large payloads, tree output, etc.)."""
    item = db.get(Item, item_id)
    if not item or item.deleted_at is not None:
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
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """List snapshots for an item, filtered by kind if provided."""
    item = db.get(Item, item_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")
    query = db.query(ItemSnapshot).filter(ItemSnapshot.item_id == item_id)
    if kind:
        query = query.filter(ItemSnapshot.kind == kind)
    if not include_deleted:
        query = query.filter(ItemSnapshot.deleted_at.is_(None))
    query = query.order_by(ItemSnapshot.captured_at.desc())
    if offset:
        query = query.offset(offset)
    return query.limit(limit).all()


@router.delete("/{item_id}/snapshots/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_snapshot(item_id: UUID, snapshot_id: UUID, db: Session = Depends(get_db)):
    """Delete a single snapshot for an item."""
    snapshot = db.get(ItemSnapshot, snapshot_id)
    if not snapshot or snapshot.item_id != item_id or snapshot.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    snapshot.deleted_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: UUID, db: Session = Depends(get_db)):
    """Delete an item if it has no active relations."""
    item = db.get(Item, item_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")
    active_relation = (
        db.query(ItemRelation)
        .filter(
            ItemRelation.active.is_(True),
            or_(ItemRelation.parent_item_id == item_id, ItemRelation.child_item_id == item_id),
            ItemRelation.deleted_at.is_(None),
        )
        .first()
    )
    if active_relation:
        raise HTTPException(status_code=409, detail="Item has active relations")
    now = dt.datetime.now(dt.timezone.utc)
    item.deleted_at = now
    (
        db.query(ItemRelation)
        .filter(
            or_(ItemRelation.parent_item_id == item_id, ItemRelation.child_item_id == item_id),
            ItemRelation.deleted_at.is_(None),
        )
        .update({ItemRelation.deleted_at: now, ItemRelation.active: False}, synchronize_session=False)
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/search", response_model=list[ItemOut])
def search_items(
    payload: SearchRequest,
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Perform a multi-criteria search across type, location, props, availability."""
    query = select(Item)
    if not include_deleted:
        query = query.where(Item.deleted_at.is_(None))

    if payload.type:
        query = query.join(ItemType, Item.type_id == ItemType.id).where(
            ItemType.name == payload.type,
            ItemType.deleted_at.is_(None),
        )

    if payload.location:
        root_location = db.get(Location, payload.location.root_location_id)
        if not root_location or root_location.deleted_at is not None:
            raise HTTPException(status_code=400, detail="Location not found")
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
                ItemRelation.deleted_at.is_(None),
            )
        )
        query = query.where(in_use_filter if payload.in_use else ~in_use_filter)

    return db.execute(query).scalars().all()
