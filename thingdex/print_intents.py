from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from typing import Any, Mapping
import uuid

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from thingdex.models import PrintIntent


class PermanentDeliveryError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve(context: Mapping[str, Any], path: str) -> Any:
    value: Any = context
    for segment in path.split("."):
        if not isinstance(value, Mapping) or segment not in value:
            return None
        value = value[segment]
    return value


def resolve_intent_variables(
    props: Mapping[str, Any],
    *,
    context: Mapping[str, Any],
    bindings: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    variables = dict(props)
    variables["internal_uuid"] = str((context.get("entity") or {})["id"])
    for variable, source in (bindings or {}).items():
        value = _resolve({"props": props, **context}, source)
        if value is not None:
            variables[variable] = value
    return variables


def queue_print_intent(
    db: Session,
    *,
    entity_kind: str,
    entity_id: uuid.UUID,
    entity_version: str,
    template_id: str,
    printer_id: str,
    variables: Mapping[str, Any],
    operation: str,
) -> PrintIntent:
    intent = PrintIntent(
        id=uuid.uuid4(),
        idempotency_key=f"thingdex:{entity_kind}:{entity_id}:{operation}:{entity_version}",
        entity_kind=entity_kind,
        entity_id=entity_id,
        entity_version=entity_version,
        template_id=template_id,
        printer_id=printer_id,
        variables=dict(variables),
        state="pending",
    )
    db.add(intent)
    return intent


class PrintHubConnector:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("PRINTHUB_API_BASE", "http://printhub:8000")).rstrip("/")
        self.token = token if token is not None else os.getenv("PRINTHUB_API_TOKEN")

    def submit(self, intent: PrintIntent) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        with httpx.Client(timeout=15.0, headers=headers) as client:
            response = client.post(
                f"{self.base_url}/v1/print-jobs",
                json={
                    "printer_id": intent.printer_id,
                    "template_id": intent.template_id,
                    "variables": intent.variables,
                    "idempotency_key": intent.idempotency_key,
                    "origin": "thingdex",
                    "origin_reference": str(intent.id),
                },
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if 400 <= response.status_code < 500 and response.status_code not in {408, 429}:
                    raise PermanentDeliveryError(
                        f"PrintHub rejected the intent ({response.status_code})"
                    ) from exc
                raise
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("id"):
            raise RuntimeError("PrintHub returned an invalid job response")
        return payload


def deliver_one(
    session_factory,
    connector: PrintHubConnector,
    *,
    max_attempts: int = 10,
    lease_seconds: int = 300,
) -> bool:
    now = _now()
    with session_factory() as db:
        intent = db.execute(
            select(PrintIntent)
            .where(
                or_(
                    (
                        (PrintIntent.state == "pending")
                        & or_(
                            PrintIntent.next_attempt_at.is_(None),
                            PrintIntent.next_attempt_at <= now,
                        )
                    ),
                    (
                        (PrintIntent.state == "delivering")
                        & (PrintIntent.next_attempt_at <= now)
                    ),
                ),
            )
            .order_by(PrintIntent.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        ).scalar_one_or_none()
        if intent is None:
            return False
        intent.state = "delivering"
        intent.attempts += 1
        intent.next_attempt_at = now + timedelta(seconds=max(30, lease_seconds))
        intent.updated_at = now
        intent_id = intent.id
        db.commit()

    try:
        with session_factory() as db:
            intent = db.get(PrintIntent, intent_id)
            if intent is None:
                return True
            payload = connector.submit(intent)
            intent.state = "accepted"
            intent.printhub_job_id = str(payload["id"])
            intent.printhub_job_state = str(payload.get("status") or "accepted")
            intent.last_error = None
            intent.accepted_at = _now()
            db.commit()
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        with session_factory() as db:
            intent = db.get(PrintIntent, intent_id)
            if intent is None:
                return True
            intent.last_error = str(exc)
            if isinstance(exc, PermanentDeliveryError) or intent.attempts >= max_attempts:
                intent.state = "failed"
                intent.next_attempt_at = None
            else:
                intent.state = "pending"
                delay = min(300, 2 ** min(intent.attempts, 8))
                intent.next_attempt_at = _now() + timedelta(seconds=delay)
            db.commit()
    return True
