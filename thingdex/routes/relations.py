import datetime as dt
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from thingdex.crud import (
    IN_USE_RELATION_TYPES,
    ensure_root_location,
    is_item_in_use,
    lock_in_use_relation_graph,
)
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
    """Update relation metadata. Attach/detach endpoints own active state changes."""
    relation = db.get(ItemRelation, relation_id)
    if not relation or relation.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Relation not found")
    if (
        payload.quantity is None
        and payload.slot is None
        and payload.notes is None
    ):
        raise HTTPException(status_code=400, detail="No fields to update")

    changed = False
    if payload.quantity is not None and relation.quantity != payload.quantity:
        relation.quantity = payload.quantity
        changed = True
    if payload.slot is not None and relation.slot != payload.slot:
        relation.slot = payload.slot
        changed = True
    if payload.notes is not None and relation.notes != payload.notes:
        relation.notes = payload.notes
        changed = True
    if not changed:
        return relation
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
    if not relation or relation.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Relation not found")
    if not relation.active:
        return relation
    if relation.relation_type in IN_USE_RELATION_TYPES:
        lock_in_use_relation_graph(db)
    relation.active = False

    child = db.get(Item, relation.child_item_id)
    if not child or child.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Child item not found")

    if relation.relation_type in IN_USE_RELATION_TYPES:
        db.flush()
        if not is_item_in_use(db, child.id):
            location_id = payload.location_id
            if location_id is None:
                root = ensure_root_location(db)
                location_id = root.id
            location = db.get(Location, location_id)
            if not location or location.deleted_at is not None:
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


@router.delete("/{relation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_relation(relation_id: UUID, db: Session = Depends(get_db)):
    """Delete a relation (requires detach first for in-use relations)."""
    relation = db.get(ItemRelation, relation_id)
    if not relation or relation.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Relation not found")
    if relation.active and relation.relation_type in IN_USE_RELATION_TYPES:
        raise HTTPException(status_code=409, detail="Detach relation before deletion")
    now = dt.datetime.now(dt.timezone.utc)
    parent = db.get(Item, relation.parent_item_id)
    child = db.get(Item, relation.child_item_id)
    if parent:
        parent.updated_at = now
    if child:
        child.updated_at = now
    relation.active = False
    relation.deleted_at = now
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
