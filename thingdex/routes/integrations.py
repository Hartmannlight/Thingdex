from __future__ import annotations

from datetime import datetime
import hashlib
import hmac
import os
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from thingdex.db import SessionLocal
from thingdex.models import PrintHubStatusEvent, PrintIntent


router = APIRouter(prefix="/v1/integrations/printhub", tags=["integrations"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class PrintHubEventIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=512)
    intent_id: UUID
    sequence: int = Field(ge=1)
    job_id: str = Field(min_length=1, max_length=255)
    job_state: str = Field(min_length=1, max_length=120)
    occurred_at: datetime
    detail: dict[str, Any] = Field(default_factory=dict)


class PrintHubEventResult(BaseModel):
    result: Literal["applied", "duplicate", "stale"]
    event_id: str
    intent_id: UUID
    sequence: int


def _verify(body: bytes, signature: str | None) -> None:
    secret = os.getenv("THINGDEX_PRINTHUB_EVENT_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="PrintHub event inbox is disabled")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid PrintHub event signature")


@router.post("/events", response_model=PrintHubEventResult)
async def apply_printhub_event(
    request: Request,
    x_thingdex_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> PrintHubEventResult:
    body = await request.body()
    _verify(body, x_thingdex_signature)
    try:
        payload = PrintHubEventIn.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    existing = db.get(PrintHubStatusEvent, payload.event_id)
    if existing:
        return PrintHubEventResult(
            result="duplicate",
            event_id=payload.event_id,
            intent_id=existing.intent_id,
            sequence=existing.sequence,
        )
    intent = db.execute(
        select(PrintIntent).where(PrintIntent.id == payload.intent_id).with_for_update()
    ).scalar_one_or_none()
    if intent is None:
        raise HTTPException(status_code=404, detail="Print intent not found")
    applied = payload.sequence > intent.status_sequence
    if applied:
        intent.status_sequence = payload.sequence
        intent.printhub_job_id = payload.job_id
        intent.printhub_job_state = payload.job_state
    db.add(
        PrintHubStatusEvent(
            event_id=payload.event_id,
            intent_id=intent.id,
            sequence=payload.sequence,
            job_id=payload.job_id,
            job_state=payload.job_state,
            occurred_at=payload.occurred_at,
            payload=payload.model_dump(mode="json"),
            applied=applied,
        )
    )
    db.commit()
    return PrintHubEventResult(
        result="applied" if applied else "stale",
        event_id=payload.event_id,
        intent_id=intent.id,
        sequence=payload.sequence,
    )
