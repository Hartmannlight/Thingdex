from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from thingdex.crud import ensure_root_location, get_descendant_location_ids, get_location_path
from thingdex.db import SessionLocal
from thingdex.labeling import (
    LabelServiceError,
    container_template_id,
    fetch_template,
    label_printing_enabled,
    print_label,
)
from thingdex.models import Item, Location
from thingdex.schemas import ItemOut, LocationCreate, LocationOut, LocationPathItem, LocationUpdate

router = APIRouter(prefix="/v1/locations", tags=["locations"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=LocationOut)
def create_location(payload: LocationCreate, db: Session = Depends(get_db)):
    """Create a new location node in the location tree."""
    if payload.parent_id is None and payload.kind == "root":
        return ensure_root_location(db, name=payload.name)
    location = Location(
        name=payload.name,
        parent_id=payload.parent_id,
        kind=payload.kind,
        meta=payload.meta or {},
    )
    db.add(location)
    db.commit()
    if payload.label_print is not None:
        if not label_printing_enabled():
            raise HTTPException(status_code=400, detail="Label printing is disabled")
        template_id = container_template_id()
        try:
            template = fetch_template(template_id)
            variables = {"uuid": str(location.id), "containername": location.name}
            print_label(
                printer_id=payload.label_print.printer_id,
                template=template.get("template", {}),
                variables=variables,
                return_preview=payload.label_print.return_preview,
            )
        except LabelServiceError as exc:
            db.rollback()
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.refresh(location)
    return location


@router.get("/root", response_model=LocationOut)
def get_root_location(db: Session = Depends(get_db)):
    """Fetch or create the unique root location."""
    return ensure_root_location(db)


@router.get("/{location_id}", response_model=LocationOut)
def get_location(location_id: UUID, db: Session = Depends(get_db)):
    """Fetch a single location by ID."""
    location = db.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


@router.patch("/{location_id}", response_model=LocationOut)
def update_location(location_id: UUID, payload: LocationUpdate, db: Session = Depends(get_db)):
    """Update location metadata or move it by changing parent_id."""
    location = db.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    if payload.parent_id is not None:
        if payload.parent_id == location_id:
            raise HTTPException(status_code=400, detail="Location cannot be its own parent")
        parent = db.get(Location, payload.parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail="Parent location not found")
        location.parent_id = payload.parent_id
    if payload.name is not None:
        location.name = payload.name
    if payload.kind is not None:
        location.kind = payload.kind
    if payload.meta is not None:
        location.meta = payload.meta
    db.commit()
    db.refresh(location)
    return location


@router.get("/{location_id}/children", response_model=list[LocationOut])
def list_children(location_id: UUID, db: Session = Depends(get_db)):
    """List direct child locations for a given parent."""
    return db.query(Location).filter(Location.parent_id == location_id).all()


@router.get("/{location_id}/path", response_model=list[LocationPathItem])
def get_path(location_id: UUID, db: Session = Depends(get_db)):
    """Return the full location path from root to this node."""
    location = db.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return get_location_path(db, location_id)


@router.get("/{location_id}/items", response_model=list[ItemOut])
def list_items_in_location(
    location_id: UUID,
    include_descendants: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """List items stored in a location, optionally including descendants."""
    if include_descendants:
        location_ids = get_descendant_location_ids(db, location_id)
        return db.query(Item).filter(Item.location_id.in_(location_ids)).all()
    return db.query(Item).filter(Item.location_id == location_id).all()
