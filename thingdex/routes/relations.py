import datetime as dt
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from thingdex.crud import IN_USE_RELATION_TYPES, ensure_root_location, is_item_in_use
from thingdex.db import SessionLocal
from thingdex.models import Item, ItemRelation, Location
from thingdex.schemas import ItemRelationDetach, ItemRelationOut, ItemRelationUpdate

router = APIRouter(prefix="/v1/relations", tags=["relations"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.patch("/{relation_id}", response_model=ItemRelationOut)
def update_relation(relation_id: UUID, payload: ItemRelationUpdate, db: Session = Depends(get_db)):
    """Update relation active flag."""
    relation = db.get(ItemRelation, relation_id)
    if not relation:
        raise HTTPException(status_code=404, detail="Relation not found")
    if relation.active == payload.active:
        return relation
    relation.active = payload.active
    now = dt.datetime.now(dt.timezone.utc)
    parent = db.get(Item, relation.parent_item_id)
    child = db.get(Item, relation.child_item_id)
    if parent:
        parent.updated_at = now
    if child:
        child.updated_at = now
    db.commit()
    db.refresh(relation)
    return relation


@router.post("/{relation_id}/detach", response_model=ItemRelationOut)
def detach_relation(relation_id: UUID, payload: ItemRelationDetach, db: Session = Depends(get_db)):
    """Detach a child from a parent and place it in a location."""
    relation = db.get(ItemRelation, relation_id)
    if not relation:
        raise HTTPException(status_code=404, detail="Relation not found")
    if not relation.active:
        return relation
    relation.active = False

    child = db.get(Item, relation.child_item_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child item not found")

    if relation.relation_type in IN_USE_RELATION_TYPES:
        db.flush()
        if not is_item_in_use(db, child.id):
            location_id = payload.location_id
            if location_id is None:
                root = ensure_root_location(db)
                location_id = root.id
            location = db.get(Location, location_id)
            if not location:
                raise HTTPException(status_code=400, detail="Location not found")
            child.location_id = location_id

    now = dt.datetime.now(dt.timezone.utc)
    parent = db.get(Item, relation.parent_item_id)
    if parent:
        parent.updated_at = now
    child.updated_at = now
    db.commit()
    db.refresh(relation)
    return relation
