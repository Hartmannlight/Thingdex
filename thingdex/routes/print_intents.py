from __future__ import annotations

import os
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from thingdex.db import SessionLocal
from thingdex.models import PrintIntent
from thingdex.schemas import PrintIntentOut


router = APIRouter(prefix="/v1/print-intents", tags=["print-intents"])
bearer = HTTPBearer(auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    expected = os.getenv("THINGDEX_PRINT_ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Print intent administration is disabled")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing print administration token")
    if not secrets.compare_digest(credentials.credentials, expected):
        raise HTTPException(status_code=403, detail="Invalid print administration token")


@router.get("", response_model=list[PrintIntentOut], dependencies=[Depends(authorize)])
def list_print_intents(
    state: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(PrintIntent)
    if state:
        query = query.filter(PrintIntent.state == state)
    return query.order_by(PrintIntent.created_at.desc()).limit(limit).all()


@router.get("/{intent_id}", response_model=PrintIntentOut, dependencies=[Depends(authorize)])
def get_print_intent(intent_id: UUID, db: Session = Depends(get_db)):
    intent = db.get(PrintIntent, intent_id)
    if intent is None:
        raise HTTPException(status_code=404, detail="Print intent not found")
    return intent


@router.post("/{intent_id}/retry", response_model=PrintIntentOut, dependencies=[Depends(authorize)])
def retry_print_intent(intent_id: UUID, db: Session = Depends(get_db)):
    intent = db.get(PrintIntent, intent_id)
    if intent is None:
        raise HTTPException(status_code=404, detail="Print intent not found")
    if intent.state != "failed":
        raise HTTPException(status_code=409, detail="Only failed print intents can be retried")
    intent.state = "pending"
    # A deliberate operator retry starts a fresh bounded delivery budget.
    intent.attempts = 0
    intent.next_attempt_at = None
    intent.last_error = None
    db.commit()
    db.refresh(intent)
    return intent
