import datetime as dt
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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
from thingdex.schemas import (
    ItemOut,
    LocationCreate,
    LocationOut,
    LocationPathItem,
    LocationTreeNode,
    LocationUpdate,
)

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
    if payload.parent_id is not None:
        parent = db.get(Location, payload.parent_id)
        if not parent or parent.deleted_at is not None:
            raise HTTPException(status_code=400, detail="Parent location not found")
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
        template_id = payload.label_print.template_id
        if not template_id and isinstance(location.meta, dict):
            template_id = location.meta.get("label_template_id")
        if not template_id:
            template_id = container_template_id()
        try:
            template = fetch_template(template_id)
            variables = {
                "location_uuid": str(location.id),
                "container_name": location.name,
                "internal_uuid": str(location.id),
            }
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


@router.get("/tree", response_model=LocationTreeNode)
def get_location_tree(
    root_location_id: UUID | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Return a nested tree of locations starting at root_location_id."""
    if root_location_id is None:
        root = ensure_root_location(db)
        root_location_id = root.id
    root_location = db.get(Location, root_location_id)
    if not root_location or root_location.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Location not found")

    location_ids = get_descendant_location_ids(db, root_location_id, include_deleted=include_deleted)
    query = db.query(Location).filter(Location.id.in_(location_ids))
    if not include_deleted:
        query = query.filter(Location.deleted_at.is_(None))
    locations = query.order_by(Location.name).all()
    nodes = {
        location.id: LocationTreeNode(
            id=location.id,
            name=location.name,
            parent_id=location.parent_id,
            kind=location.kind,
            meta=location.meta,
            children=[],
        )
        for location in locations
    }

    for location in locations:
        if location.parent_id and location.parent_id in nodes:
            nodes[location.parent_id].children.append(nodes[location.id])

    for node in nodes.values():
        node.children.sort(key=lambda child: child.name)

    return nodes[root_location_id]


@router.get("/{location_id}", response_model=LocationOut)
def get_location(location_id: UUID, db: Session = Depends(get_db)):
    """Fetch a single location by ID."""
    location = db.get(Location, location_id)
    if not location or location.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


@router.patch("/{location_id}", response_model=LocationOut)
def update_location(location_id: UUID, payload: LocationUpdate, db: Session = Depends(get_db)):
    """Update location metadata or move it by changing parent_id."""
    location = db.get(Location, location_id)
    if not location or location.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Location not found")
    if payload.parent_id is not None:
        if payload.parent_id == location_id:
            raise HTTPException(status_code=400, detail="Location cannot be its own parent")
        parent = db.get(Location, payload.parent_id)
        if not parent or parent.deleted_at is not None:
            raise HTTPException(status_code=400, detail="Parent location not found")
        descendant_ids = get_descendant_location_ids(db, location_id)
        if payload.parent_id in descendant_ids:
            raise HTTPException(status_code=400, detail="Location cannot be moved into its descendant")
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
def list_children(
    location_id: UUID,
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """List direct child locations for a given parent."""
    query = db.query(Location).filter(Location.parent_id == location_id).order_by(Location.name)
    if not include_deleted:
        query = query.filter(Location.deleted_at.is_(None))
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


@router.get("/{location_id}/path", response_model=list[LocationPathItem])
def get_path(location_id: UUID, db: Session = Depends(get_db)):
    """Return the full location path from root to this node."""
    location = db.get(Location, location_id)
    if not location or location.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Location not found")
    return get_location_path(db, location_id)


@router.get("/{location_id}/items", response_model=list[ItemOut])
def list_items_in_location(
    location_id: UUID,
    include_descendants: bool = Query(default=False),
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """List items stored in a location, optionally including descendants."""
    location = db.get(Location, location_id)
    if not location or location.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Location not found")
    if include_descendants:
        location_ids = get_descendant_location_ids(db, location_id)
        query = db.query(Item).filter(Item.location_id.in_(location_ids))
    else:
        query = db.query(Item).filter(Item.location_id == location_id)
    if not include_deleted:
        query = query.filter(Item.deleted_at.is_(None))
    query = query.order_by(Item.created_at.desc())
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(location_id: UUID, db: Session = Depends(get_db)):
    """Delete a location if it has no items in its subtree."""
    location = db.get(Location, location_id)
    if not location or location.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Location not found")
    if location.kind == "root" or (isinstance(location.meta, dict) and location.meta.get("is_root")):
        raise HTTPException(status_code=400, detail="Root location cannot be deleted")
    location_ids = get_descendant_location_ids(db, location_id)
    if (
        db.query(Item.id)
        .filter(Item.location_id.in_(location_ids), Item.deleted_at.is_(None))
        .first()
    ):
        raise HTTPException(status_code=409, detail="Location has items in its subtree")
    now = dt.datetime.now(dt.timezone.utc)
    (
        db.query(Location)
        .filter(Location.id.in_(location_ids), Location.deleted_at.is_(None))
        .update({Location.deleted_at: now}, synchronize_session=False)
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
