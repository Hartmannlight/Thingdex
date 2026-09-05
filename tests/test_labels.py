import hashlib
import hmac
import json
from datetime import datetime, timezone


def _create_item_type(client, name="LabeledType"):
    response = client.post(
        "/v1/item-types",
        json={
            "name": name,
            "schema": {
                "fields": {"serial": {"type": "string", "required": True}},
                "allow_additional": False,
            },
            "ui": {},
            "label_template_id": "item-test",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _get_root_location(client):
    response = client.get("/v1/locations/root")
    assert response.status_code == 200, response.text
    return response.json()


ADMIN = {"Authorization": "Bearer test-print-admin-token"}


def test_template_variables_support_typed_source_hints():
    from thingdex.labeling import build_template_variables, validate_template_against_schema

    template = {
        "variables": [
            {
                "name": "title",
                "mode": "required",
                "type": "text",
                "source_hint": "entity.display_name",
            },
            {"name": "identifier", "mode": "required", "source_hint": "entity.id"},
            {"name": "serial", "mode": "required"},
        ]
    }
    schema = {"fields": {"serial": {"type": "string", "required": True}}}

    assert validate_template_against_schema(template, schema) == []
    assert build_template_variables(
        template,
        {"serial": "SN-42"},
        context={"entity": {"display_name": "Cordless drill", "id": "item-42"}},
    ) == {"title": "Cordless drill", "identifier": "item-42", "serial": "SN-42"}


def test_item_type_template_reference_does_not_require_printhub(label_client):
    created = _create_item_type(label_client, name="OfflineTemplateReference")
    assert created["label_template_id"] == "item-test"

    updated = label_client.patch(
        f"/v1/item-types/{created['id']}",
        json={"label_template_id": "future-template"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["label_template_id"] == "future-template"


def test_manual_item_and_location_reprints_are_durably_queued(label_client):
    root = _get_root_location(label_client)
    item_type = _create_item_type(label_client)
    item = label_client.post(
        "/v1/items",
        json={
            "type_id": item_type["id"],
            "location_id": root["id"],
            "props": {"serial": "L-1"},
        },
    ).json()["data"]

    item_label = label_client.post(
        "/v1/labels/print",
        json={"printer_id": "demo", "item_id": item["id"]},
    )
    assert item_label.status_code == 202, item_label.text
    assert item_label.json()["status"] == "queued"
    intent = label_client.get(
        f"/v1/print-intents/{item_label.json()['job_id']}", headers=ADMIN
    )
    assert intent.status_code == 200
    assert intent.json()["entity_id"] == item["id"]
    assert intent.json()["state"] == "pending"
    assert "variables" not in intent.json()

    location = label_client.post(
        "/v1/locations",
        json={
            "name": "Shelf",
            "parent_id": root["id"],
            "kind": "shelf",
            "meta": {"label_template_id": "container-test"},
        },
    ).json()["data"]
    location_label = label_client.post(
        "/v1/labels/print",
        json={"printer_id": "demo", "location_id": location["id"]},
    )
    assert location_label.status_code == 202, location_label.text
    intent = label_client.get(
        f"/v1/print-intents/{location_label.json()['job_id']}", headers=ADMIN
    ).json()
    assert intent["entity_id"] == location["id"]
    assert intent["template_id"] == "container-test"


def test_create_commits_inventory_and_outbox_without_calling_printhub(label_client, monkeypatch):
    from thingdex.print_intents import PrintHubConnector

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("The request path must not call PrintHub")

    monkeypatch.setattr(PrintHubConnector, "submit", fail_if_called)
    root = _get_root_location(label_client)
    item_type = _create_item_type(label_client, name="QueuedOnCreate")

    created_item = label_client.post(
        "/v1/items",
        json={
            "type_id": item_type["id"],
            "location_id": root["id"],
            "props": {"serial": "Q-1"},
            "label_print": {"printer_id": "demo"},
        },
    )
    assert created_item.status_code == 200, created_item.text
    side_effect = created_item.json()["side_effects"]["label_print"]
    assert side_effect["success"] is True
    assert side_effect["result"]["job_state"] == "pending"
    assert label_client.get(
        f"/v1/print-intents/{side_effect['result']['job_id']}", headers=ADMIN
    ).status_code == 200

    created_location = label_client.post(
        "/v1/locations",
        json={
            "name": "Drawer",
            "parent_id": root["id"],
            "kind": "container",
            "label_print": {"printer_id": "demo", "template_id": "container-test"},
        },
    )
    assert created_location.status_code == 200, created_location.text
    assert created_location.json()["side_effects"]["label_print"]["success"] is True


def test_label_profiles_queue_new_entities_with_stable_destinations(label_client, monkeypatch):
    from thingdex.routes import label_profiles as profile_routes

    def fake_fetch_template(template_id: str):
        variables = (
            [{"name": "serial", "mode": "required"}]
            if template_id == "item-auto"
            else [{"name": "container_name", "mode": "required"}]
        )
        return {"template": {"id": template_id}, "variables": variables}

    monkeypatch.setattr(profile_routes, "fetch_template", fake_fetch_template)
    root = _get_root_location(label_client)
    item_type = _create_item_type(label_client, name="AutoProfileType")
    assert label_client.post(
        "/v1/label-profiles",
        json={
            "name": "Items",
            "entity_kind": "item",
            "item_type_id": item_type["id"],
            "template_id": "item-auto",
            "printer_id": "packing-desk",
        },
    ).status_code == 201
    assert label_client.post(
        "/v1/label-profiles",
        json={
            "name": "Containers",
            "entity_kind": "location",
            "location_kind": "container",
            "template_id": "location-auto",
            "printer_id": "warehouse",
        },
    ).status_code == 201

    item = label_client.post(
        "/v1/items",
        json={
            "type_id": item_type["id"],
            "location_id": root["id"],
            "props": {"serial": "AUTO-1"},
        },
    ).json()
    item_job = item["side_effects"]["label_print"]["result"]["job_id"]
    item_intent = label_client.get(f"/v1/print-intents/{item_job}", headers=ADMIN).json()
    assert item_intent["template_id"] == "item-auto"
    assert item_intent["printer_id"] == "packing-desk"

    location = label_client.post(
        "/v1/locations",
        json={"name": "Auto bin", "parent_id": root["id"], "kind": "container"},
    ).json()
    location_job = location["side_effects"]["label_print"]["result"]["job_id"]
    location_intent = label_client.get(
        f"/v1/print-intents/{location_job}", headers=ADMIN
    ).json()
    assert location_intent["template_id"] == "location-auto"
    assert location_intent["printer_id"] == "warehouse"


def test_print_intent_admin_endpoints_fail_closed_without_valid_token(label_client):
    assert label_client.get("/v1/print-intents").status_code == 401
    assert label_client.get(
        "/v1/print-intents", headers={"Authorization": "Bearer wrong"}
    ).status_code == 403


def test_signed_printhub_events_are_idempotent_and_sequence_guarded(label_client):
    root = _get_root_location(label_client)
    item_type = _create_item_type(label_client, name="EventType")
    created = label_client.post(
        "/v1/items",
        json={
            "type_id": item_type["id"],
            "location_id": root["id"],
            "props": {"serial": "EVENT-1"},
            "label_print": {"printer_id": "demo"},
        },
    ).json()
    intent_id = created["side_effects"]["label_print"]["result"]["job_id"]

    def signed_event(event_id: str, sequence: int, state: str):
        body = json.dumps(
            {
                "event_id": event_id,
                "intent_id": intent_id,
                "sequence": sequence,
                "job_id": "printhub-job",
                "job_state": state,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "detail": {},
            },
            separators=(",", ":"),
        ).encode()
        signature = "sha256=" + hmac.new(
            b"test-event-secret", body, hashlib.sha256
        ).hexdigest()
        return label_client.post(
            "/v1/integrations/printhub/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Thingdex-Signature": signature,
            },
        )

    applied = signed_event("event-2", 2, "submitted")
    duplicate = signed_event("event-2", 2, "submitted")
    stale = signed_event("event-1", 1, "preparing")
    assert applied.json()["result"] == "applied"
    assert duplicate.json()["result"] == "duplicate"
    assert stale.json()["result"] == "stale"
    intent = label_client.get(f"/v1/print-intents/{intent_id}", headers=ADMIN).json()
    assert intent["printhub_job_state"] == "submitted"
