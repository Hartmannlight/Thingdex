import datetime as dt
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from thingdex.crud import (
    ensure_root_location,
    get_descendant_location_ids,
    get_location_path,
    get_root_location as find_root_location,
)
from thingdex.db import SessionLocal
from thingdex.labeling import (
    LabelServiceError,
    build_template_variables,
    container_template_id,
    fetch_template,
    label_printing_enabled,
    print_label,
    required_template_variables,
)
from thingdex.models import Item, LabelProfile, Location
from thingdex.schemas import (
    ItemOut,
    LabelPrintRequest,
    LocationCreate,
    LocationCreateResponse,
    LocationOut,
    LocationPathItem,
    LocationTreeNode,
    LocationUpdate,
    SideEffectResult,
    SideEffects,
)

router = APIRouter(prefix="/v1/locations", tags=["locations"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=LocationCreateResponse)
def create_location(payload: LocationCreate, db: Session = Depends(get_db)):
    """Create a new location node in the location tree."""
    if payload.parent_id is None and payload.kind == "root":
        location = ensure_root_location(db, name=payload.name)
        return LocationCreateResponse(data=location)
    if payload.parent_id is None:
        raise HTTPException(status_code=400, detail="parent_id is required for non-root locations")
    if payload.kind == "root":
        raise HTTPException(status_code=400, detail="Root location cannot have a parent")
    parent = db.get(Location, payload.parent_id)
    if not parent or parent.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Parent location not found")

    profile = (
        db.query(LabelProfile)
        .filter(
            LabelProfile.entity_kind == "location",
            LabelProfile.location_kind.in_([payload.kind, "*"]),
            LabelProfile.enabled.is_(True),
            LabelProfile.auto_print.is_(True),
        )
        .order_by(LabelProfile.location_kind.desc())
        .first()
    )
    label_request = payload.label_print
    profile_bindings: dict[str, str] = {}
    if label_request is None and profile is not None:
        label_request = LabelPrintRequest(
            printer_id=profile.printer_id,
            template_id=profile.template_id,
        )
        profile_bindings = dict(profile.bindings or {})

    location = Location(
        name=payload.name,
        parent_id=payload.parent_id,
        kind=payload.kind,
        meta=payload.meta or {},
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    label_print_result = None
    if label_request is not None:
        label_print_result = SideEffectResult(requested=True, success=False)
        if not label_printing_enabled():
            label_print_result.error = "Label printing is disabled"
            return LocationCreateResponse(
                data=location,
                side_effects=SideEffects(label_print=label_print_result),
            )
        try:
            template_id = label_request.template_id
            if not template_id and isinstance(location.meta, dict):
                template_id = location.meta.get("label_template_id")
            if not template_id:
                template_id = container_template_id()
            template = fetch_template(template_id)
            base_variables = {
                "location_uuid": str(location.id),
                "container_name": location.name,
                "internal_uuid": str(location.id),
            }
            variables = build_template_variables(
                template,
                location.meta or {},
                context={
                    "entity": {
                        "id": str(location.id),
                        "display_name": location.name,
                    },
                    "location": {
                        "id": str(location.id),
                        "name": location.name,
                        "kind": location.kind,
                        "meta": location.meta or {},
                    },
                },
                bindings=profile_bindings,
            )
            variables.update(base_variables)
            missing = [name for name in required_template_variables(template) if name not in variables]
            if missing:
                label_print_result.error = (
                    "Missing required template variables: "
                    f"{', '.join(missing)}"
                )
                return LocationCreateResponse(
                    data=location,
                    side_effects=SideEffects(label_print=label_print_result),
                )
            print_response = print_label(
                printer_id=label_request.printer_id,
                template=template.get("template", {}),
                variables=variables,
                return_preview=label_request.return_preview,
                template_id=template_id,
                idempotency_key=f"thingdex:location:{location.id}:create",
                origin="thingdex",
            )
            label_print_result.success = True
            label_print_result.result = print_response
        except LabelServiceError as exc:
            label_print_result.error = str(exc)
    return LocationCreateResponse(
        data=location,
        side_effects=SideEffects(label_print=label_print_result),
    )


@router.get("/root", response_model=LocationOut)
def get_root_location(db: Session = Depends(get_db)):
    """Fetch the unique root location."""
    root = find_root_location(db)
    if root is None:
        raise HTTPException(status_code=404, detail="Root location not found")
    return root


@router.post("/root/bootstrap", response_model=LocationOut)
def bootstrap_root_location(db: Session = Depends(get_db)):
    """Create the unique root location if it does not exist."""
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
    is_root = location.parent_id is None and location.kind == "root"
    changed_fields = payload.model_fields_set
    if is_root:
        if "parent_id" in changed_fields:
            raise HTTPException(status_code=400, detail="Root location cannot be moved")
        if "kind" in changed_fields and payload.kind != "root":
            raise HTTPException(status_code=400, detail="Root location kind cannot be changed")
    elif "kind" in changed_fields and payload.kind == "root":
        raise HTTPException(status_code=400, detail="Only the root location can use kind 'root'")

    if "parent_id" in changed_fields:
        if payload.parent_id is None:
            raise HTTPException(status_code=400, detail="Non-root locations require a parent")
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
