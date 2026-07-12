from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from thingdex.db import SessionLocal
from thingdex.labeling import LabelServiceError, fetch_template, validate_template_against_schema
from thingdex.models import ItemType, LabelProfile
from thingdex.schemas import LabelProfileCreate, LabelProfileOut, LabelProfileUpdate


router = APIRouter(prefix="/v1/label-profiles", tags=["label-profiles"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _validate_selector(payload: LabelProfileCreate) -> ItemType | None:
    if payload.entity_kind == "item":
        if payload.item_type_id is None or payload.location_kind is not None:
            raise HTTPException(status_code=400, detail="Item profiles require only item_type_id")
    elif payload.location_kind is None or payload.item_type_id is not None:
        raise HTTPException(status_code=400, detail="Location profiles require only location_kind")
    return None


def _validate_template(payload: LabelProfileCreate, db: Session) -> None:
    try:
        template = fetch_template(payload.template_id)
    except LabelServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if payload.entity_kind != "item" or payload.item_type_id is None:
        return
    item_type = db.get(ItemType, payload.item_type_id)
    if not item_type or item_type.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Item type not found")
    missing = validate_template_against_schema(template, item_type.schema or {}, bindings=payload.bindings)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Template variables cannot be populated: {', '.join(missing)}",
        )


@router.post("", response_model=LabelProfileOut, status_code=status.HTTP_201_CREATED)
def create_label_profile(payload: LabelProfileCreate, db: Session = Depends(get_db)):
    _validate_selector(payload)
    _validate_template(payload, db)
    profile = LabelProfile(**payload.model_dump())
    db.add(profile)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A label profile already exists for this selector") from exc
    db.refresh(profile)
    return profile


@router.get("", response_model=list[LabelProfileOut])
def list_label_profiles(db: Session = Depends(get_db)):
    return db.query(LabelProfile).order_by(LabelProfile.name).all()


@router.get("/{profile_id}", response_model=LabelProfileOut)
def get_label_profile(profile_id: UUID, db: Session = Depends(get_db)):
    profile = db.get(LabelProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Label profile not found")
    return profile


@router.patch("/{profile_id}", response_model=LabelProfileOut)
def update_label_profile(profile_id: UUID, payload: LabelProfileUpdate, db: Session = Depends(get_db)):
    profile = db.get(LabelProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Label profile not found")
    values = payload.model_dump(exclude_unset=True)
    candidate = LabelProfileCreate(
        name=values.get("name", profile.name),
        entity_kind=profile.entity_kind,
        item_type_id=profile.item_type_id,
        location_kind=profile.location_kind,
        template_id=values.get("template_id", profile.template_id),
        printer_id=values.get("printer_id", profile.printer_id),
        auto_print=values.get("auto_print", profile.auto_print),
        bindings=values.get("bindings", profile.bindings or {}),
        enabled=values.get("enabled", profile.enabled),
    )
    if "template_id" in values or "bindings" in values:
        _validate_template(candidate, db)
    for key, value in values.items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_label_profile(profile_id: UUID, db: Session = Depends(get_db)):
    profile = db.get(LabelProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Label profile not found")
    db.delete(profile)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
