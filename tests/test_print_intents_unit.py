from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from thingdex.models import PrintIntent
from thingdex.print_intents import (
    PermanentDeliveryError,
    deliver_one,
    queue_print_intent,
    resolve_intent_variables,
)
from thingdex.routes.print_intents import retry_print_intent


@compiles(JSONB, "sqlite")
def _jsonb_as_json(_type, _compiler, **_kwargs):
    return "JSON"


def _sessions():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    PrintIntent.__table__.create(engine)
    return sessionmaker(bind=engine)


def _intent(sessions):
    entity_id = uuid.uuid4()
    with sessions() as db:
        intent = queue_print_intent(
            db,
            entity_kind="item",
            entity_id=entity_id,
            entity_version="1",
            template_id="asset",
            printer_id="shipping",
            variables={"serial": "SN-1"},
            operation="create",
        )
        intent_id = intent.id
        db.commit()
    return intent_id


def test_variable_snapshot_resolves_bindings_without_printhub() -> None:
    result = resolve_intent_variables(
        {"serial": "SN-1"},
        context={"entity": {"id": "item-1", "display_name": "Drill"}},
        bindings={"title": "entity.display_name", "identifier": "entity.id"},
    )
    assert result == {
        "serial": "SN-1",
        "internal_uuid": "item-1",
        "title": "Drill",
        "identifier": "item-1",
    }


def test_worker_accepts_outbox_entry_once_and_preserves_idempotency_key() -> None:
    sessions = _sessions()
    intent_id = _intent(sessions)

    class Connector:
        calls = []

        def submit(self, intent):
            self.calls.append(intent.idempotency_key)
            return {"id": "printhub-1", "status": "queued"}

    connector = Connector()
    assert deliver_one(sessions, connector)
    assert not deliver_one(sessions, connector)
    with sessions() as db:
        saved = db.get(PrintIntent, intent_id)
        assert saved.state == "accepted"
        assert saved.printhub_job_id == "printhub-1"
    assert len(connector.calls) == 1
    assert connector.calls[0].startswith("thingdex:item:")


def test_worker_schedules_failures_and_stops_at_attempt_limit() -> None:
    sessions = _sessions()
    intent_id = _intent(sessions)

    class Connector:
        def submit(self, _intent):
            raise RuntimeError("PrintHub offline")

    assert deliver_one(sessions, Connector(), max_attempts=1)
    with sessions() as db:
        saved = db.get(PrintIntent, intent_id)
        assert saved.state == "failed"
        assert saved.attempts == 1
        assert saved.next_attempt_at is None
        assert saved.last_error == "PrintHub offline"


def test_expired_delivery_lease_is_reclaimed_after_worker_crash() -> None:
    sessions = _sessions()
    intent_id = _intent(sessions)
    with sessions() as db:
        intent = db.get(PrintIntent, intent_id)
        intent.state = "delivering"
        intent.next_attempt_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        db.commit()

    class Connector:
        def submit(self, _intent):
            return {"id": "same-idempotent-job", "status": "queued"}

    assert deliver_one(sessions, Connector())
    with sessions() as db:
        assert db.get(PrintIntent, intent_id).state == "accepted"


def test_permanent_rejection_does_not_enter_retry_loop() -> None:
    sessions = _sessions()
    intent_id = _intent(sessions)

    class Connector:
        def submit(self, _intent):
            raise PermanentDeliveryError("invalid template")

    assert deliver_one(sessions, Connector(), max_attempts=10)
    with sessions() as db:
        saved = db.get(PrintIntent, intent_id)
        assert saved.state == "failed"
        assert saved.attempts == 1


def test_operator_retry_starts_a_fresh_bounded_attempt_budget() -> None:
    sessions = _sessions()
    intent_id = _intent(sessions)
    with sessions() as db:
        intent = db.get(PrintIntent, intent_id)
        intent.state = "failed"
        intent.attempts = 5
        intent.last_error = "PrintHub offline"
        db.commit()

        retried = retry_print_intent(intent_id, db)

        assert retried.state == "pending"
        assert retried.attempts == 0
        assert retried.last_error is None
