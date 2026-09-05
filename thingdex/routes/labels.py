from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from thingdex.db import SessionLocal
from thingdex.labeling import label_printing_enabled
from thingdex.models import Item, ItemType, LabelProfile, Location
from thingdex.print_intents import queue_print_intent, resolve_intent_variables
from thingdex.schemas import LabelPrintResult, LabelReprintRequest


router = APIRouter(prefix="/v1/labels", tags=["labels"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _queued(intent, printer_id: str) -> LabelPrintResult:
    return LabelPrintResult(
        status="queued",
        printer_id=printer_id,
        bytes_sent=0,
        job_id=str(intent.id),
        job_state="pending",
    )


@router.post("/print", response_model=LabelPrintResult, status_code=202)
def print_label_for_entity(payload: LabelReprintRequest, db: Session = Depends(get_db)):
    """Durably queue a label without requiring PrintHub during the request."""
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
        profile = (
            db.query(LabelProfile)
            .filter(
                LabelProfile.entity_kind == "item",
                LabelProfile.item_type_id == item_type.id,
                LabelProfile.enabled.is_(True),
            )
            .one_or_none()
        )
        template_id = (
            payload.template_id
            or (profile.template_id if profile else None)
            or item_type.label_template_id
        )
        if not template_id:
            raise HTTPException(status_code=400, detail="Item type has no label_template_id")
        location = db.get(Location, item.location_id) if item.location_id else None
        context = {
            "entity": {
                "id": str(item.id),
                "display_name": item.description or item_type.name,
                "description": item.description or "",
                "status": item.status,
            },
            "item": {"id": str(item.id), "type": item_type.name},
            "location": {
                "id": str(location.id) if location else None,
                "name": location.name if location else None,
            },
        }
        variables = resolve_intent_variables(
            item.props or {},
            context=context,
            bindings=dict(profile.bindings or {}) if profile else None,
        )
        version = f"{item.updated_at.isoformat()}:{uuid4()}"
        intent = queue_print_intent(
            db,
            entity_kind="item",
            entity_id=item.id,
            entity_version=version,
            template_id=template_id,
            printer_id=payload.printer_id,
            variables=variables,
            operation="reprint",
        )
        db.commit()
        return _queued(intent, payload.printer_id)

    location = db.get(Location, payload.location_id)
    if not location or location.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Location not found")
    profile = (
        db.query(LabelProfile)
        .filter(
            LabelProfile.entity_kind == "location",
            LabelProfile.location_kind.in_([location.kind, "*"]),
            LabelProfile.enabled.is_(True),
        )
        .order_by(LabelProfile.location_kind.desc())
        .first()
    )
    template_id = payload.template_id or (profile.template_id if profile else None)
    if not template_id and isinstance(location.meta, dict):
        template_id = location.meta.get("label_template_id")
    if not template_id:
        raise HTTPException(status_code=400, detail="Location has no label_template_id")
    context = {
        "entity": {"id": str(location.id), "display_name": location.name},
        "location": {
            "id": str(location.id),
            "name": location.name,
            "kind": location.kind,
            "meta": location.meta or {},
        },
    }
    variables = resolve_intent_variables(
        location.meta or {},
        context=context,
        bindings=dict(profile.bindings or {}) if profile else None,
    )
    variables.update(
        {
            "location_uuid": str(location.id),
            "container_name": location.name,
            "internal_uuid": str(location.id),
        }
    )
    version = f"{location.id}:{uuid4()}"
    intent = queue_print_intent(
        db,
        entity_kind="location",
        entity_id=location.id,
        entity_version=version,
        template_id=template_id,
        printer_id=payload.printer_id,
        variables=variables,
        operation="reprint",
    )
    db.commit()
    return _queued(intent, payload.printer_id)
