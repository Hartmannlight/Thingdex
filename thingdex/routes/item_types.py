from uuid import UUID

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from thingdex.db import SessionLocal
from thingdex.labeling import LabelServiceError, fetch_template, validate_template_against_schema
from thingdex.models import Item, ItemType
from thingdex.schemas import ItemTypeCreate, ItemTypeOut, ItemTypeUpdate

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
    if payload.label_template_id:
        try:
            template = fetch_template(payload.label_template_id)
        except LabelServiceError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        missing = validate_template_against_schema(template, payload.schema_ or {})
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
        schema=payload.schema_ or {},
        ui=payload.ui or {},
        label_template_id=payload.label_template_id,
    )
    db.add(item_type)
    db.commit()
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
    if payload.name is not None:
        item_type.name = payload.name
    if payload.schema_ is not None:
        if item_type.label_template_id:
            try:
                template = fetch_template(item_type.label_template_id)
            except LabelServiceError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            missing = validate_template_against_schema(template, payload.schema_)
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Template variables missing or not required in schema: "
                        f"{', '.join(missing)}"
                    ),
                )
        item_type.schema = payload.schema_
    if payload.ui is not None:
        item_type.ui = payload.ui
    if payload.label_template_id is not None:
        if payload.label_template_id == "":
            item_type.label_template_id = None
        else:
            try:
                template = fetch_template(payload.label_template_id)
            except LabelServiceError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            missing = validate_template_against_schema(template, item_type.schema or {})
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Template variables missing or not required in schema: "
                        f"{', '.join(missing)}"
                    ),
                )
            item_type.label_template_id = payload.label_template_id
    db.commit()
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
