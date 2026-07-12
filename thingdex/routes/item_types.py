from uuid import UUID

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from thingdex.db import SessionLocal
from thingdex.labeling import LabelServiceError, fetch_template, validate_template_against_schema
from thingdex.models import Item, ItemType
from thingdex.schemas import ItemTypeCreate, ItemTypeOut, ItemTypeUpdate
from thingdex.validation import SchemaValidationError, validate_item_type_schema, validate_props

router = APIRouter(prefix="/v1/item-types", tags=["item-types"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=ItemTypeOut)
def create_item_type(payload: ItemTypeCreate, db: Session = Depends(get_db)):
    """Create a new item type definition with schema and UI hints."""
    item_schema = payload.schema_ or {}
    try:
        validate_item_type_schema(item_schema)
    except SchemaValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors) from exc
    if payload.label_template_id:
        try:
            template = fetch_template(payload.label_template_id)
        except LabelServiceError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        missing = validate_template_against_schema(template, item_schema)
        if missing:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Template variables missing or not required in schema: "
                    f"{', '.join(missing)}"
                ),
            )
    item_type = ItemType(
        name=payload.name,
        schema=item_schema,
        ui=payload.ui or {},
        label_template_id=payload.label_template_id,
    )
    db.add(item_type)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Item type name already exists") from exc
    db.refresh(item_type)
    return item_type


@router.get("", response_model=list[ItemTypeOut])
def list_item_types(
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """List all item types."""
    query = db.query(ItemType).order_by(ItemType.name)
    if not include_deleted:
        query = query.filter(ItemType.deleted_at.is_(None))
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


@router.get("/{item_type_id}", response_model=ItemTypeOut)
def get_item_type(item_type_id: UUID, db: Session = Depends(get_db)):
    """Fetch a single item type by ID."""
    item_type = db.get(ItemType, item_type_id)
    if not item_type or item_type.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item type not found")
    return item_type


@router.patch("/{item_type_id}", response_model=ItemTypeOut)
def update_item_type(item_type_id: UUID, payload: ItemTypeUpdate, db: Session = Depends(get_db)):
    """Update name/schema/ui for an existing item type."""
    item_type = db.get(ItemType, item_type_id)
    if not item_type or item_type.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item type not found")
    target_schema = payload.schema_ if payload.schema_ is not None else (item_type.schema or {})
    target_template_id = item_type.label_template_id
    if "label_template_id" in payload.model_fields_set:
        target_template_id = payload.label_template_id or None

    try:
        validate_item_type_schema(target_schema)
    except SchemaValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors) from exc

    if target_template_id:
        try:
            template = fetch_template(target_template_id)
        except LabelServiceError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        missing = validate_template_against_schema(template, target_schema)
        if missing:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Template variables missing or not required in schema: "
                    f"{', '.join(missing)}"
                ),
            )

    if payload.schema_ is not None:
        invalid_items: list[dict[str, object]] = []
        items = (
            db.query(Item)
            .filter(Item.type_id == item_type_id, Item.deleted_at.is_(None))
            .yield_per(200)
        )
        for item in items:
            try:
                validate_props(target_schema, item.props, partial=False)
            except SchemaValidationError as exc:
                invalid_items.append({"item_id": str(item.id), "errors": exc.errors})
                if len(invalid_items) >= 20:
                    break
        if invalid_items:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Schema change would invalidate existing items",
                    "items": invalid_items,
                },
            )

    if payload.name is not None:
        item_type.name = payload.name
    if payload.schema_ is not None:
        item_type.schema = target_schema
    if payload.ui is not None:
        item_type.ui = payload.ui
    if "label_template_id" in payload.model_fields_set:
        item_type.label_template_id = target_template_id
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Item type name already exists") from exc
    db.refresh(item_type)
    return item_type


@router.delete("/{item_type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item_type(item_type_id: UUID, db: Session = Depends(get_db)):
    """Delete an item type if no items reference it."""
    item_type = db.get(ItemType, item_type_id)
    if not item_type or item_type.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item type not found")
    if db.query(Item.id).filter(Item.type_id == item_type_id, Item.deleted_at.is_(None)).first():
        raise HTTPException(status_code=409, detail="Item type has existing items")
    item_type.deleted_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
