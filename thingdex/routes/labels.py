from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from thingdex.db import SessionLocal
from thingdex.labeling import (
    LabelServiceError,
    build_template_variables,
    fetch_template,
    label_printing_enabled,
    print_label,
    required_template_variables,
)
from thingdex.models import Item, ItemType, Location
from thingdex.schemas import LabelReprintRequest

router = APIRouter(prefix="/v1/labels", tags=["labels"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/print")
def print_label_for_entity(payload: LabelReprintRequest, db: Session = Depends(get_db)):
    """Print a label for an item or location using stored template configuration."""
    if not label_printing_enabled():
        raise HTTPException(status_code=400, detail="Label printing is disabled")
    if bool(payload.item_id) == bool(payload.location_id):
        raise HTTPException(status_code=400, detail="Provide exactly one of item_id or location_id")

    if payload.item_id:
        item = db.get(Item, payload.item_id)
        if not item or item.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Item not found")
        item_type = db.get(ItemType, item.type_id)
        if not item_type or item_type.deleted_at is not None:
            raise HTTPException(status_code=400, detail="Item type not found")
        template_id = payload.template_id or item_type.label_template_id
        if not template_id:
            raise HTTPException(status_code=400, detail="Item type has no label_template_id")
        try:
            template = fetch_template(template_id)
        except LabelServiceError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        required_vars = [
            name for name in required_template_variables(template) if name != "internal_uuid"
        ]
        props = item.props or {}
        missing = [name for name in required_vars if name not in props]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required template variables in props: {', '.join(missing)}",
            )
        variables = build_template_variables(template, props)
        variables["internal_uuid"] = str(item.id)
        try:
            return print_label(
                printer_id=payload.printer_id,
                template=template.get("template", {}),
                variables=variables,
                return_preview=payload.return_preview,
            )
        except LabelServiceError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    location = db.get(Location, payload.location_id)
    if not location or location.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Location not found")
    template_id = None
    if isinstance(location.meta, dict):
        template_id = location.meta.get("label_template_id")
    if not template_id:
        template_id = payload.template_id
    if not template_id:
        raise HTTPException(status_code=400, detail="Location has no label_template_id")
    try:
        template = fetch_template(template_id)
    except LabelServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    required_vars = required_template_variables(template)
    variables = {
        "location_uuid": str(location.id),
        "container_name": location.name,
        "internal_uuid": str(location.id),
    }
    missing = [name for name in required_vars if name not in variables]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required template variables for location: {', '.join(missing)}",
        )
    try:
        return print_label(
            printer_id=payload.printer_id,
            template=template.get("template", {}),
            variables=variables,
            return_preview=payload.return_preview,
        )
    except LabelServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
