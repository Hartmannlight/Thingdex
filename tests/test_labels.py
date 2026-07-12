def _create_item_type(client, name="LabeledType"):
    payload = {
        "name": name,
        "schema": {
            "fields": {
                "serial": {"type": "string", "required": True},
            },
            "allow_additional": False,
        },
        "ui": {},
        "label_template_id": "item-test",
    }
    response = client.post("/v1/item-types", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _get_root_location(client):
    response = client.get("/v1/locations/root")
    assert response.status_code == 200, response.text
    return response.json()


def test_template_variables_support_typed_source_hints():
    from thingdex.labeling import build_template_variables, validate_template_against_schema

    template = {
        "variables": [
            {"name": "title", "mode": "required", "type": "text", "source_hint": "entity.display_name"},
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


def test_label_print_item_and_location(label_client, monkeypatch):
    from thingdex import labeling
    from thingdex.routes import item_types as item_types_routes
    from thingdex.routes import items as items_routes
    from thingdex.routes import labels as labels_routes
    from thingdex.routes import locations as locations_routes

    def fake_fetch_template(template_id: str):
        if template_id == "container-test":
            return {
                "template": {"id": template_id},
                "variables": [
                    {"name": "location_uuid", "mode": "required"},
                    {"name": "container_name", "mode": "required"},
                ],
            }
        return {
            "template": {"id": template_id},
            "variables": [{"name": "serial", "mode": "required"}],
        }

    print_calls = []

    def fake_print_label(*, printer_id, template, variables, return_preview=None, **kwargs):
        print_calls.append(
            {
                "printer_id": printer_id,
                "template": template,
                "variables": variables,
                "return_preview": return_preview,
            }
        )
        return {
            "printer_id": printer_id,
            "bytes_sent": 42,
            "preview_png_base64": "preview" if return_preview else None,
        }

    monkeypatch.setattr(labeling, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(labeling, "print_label", fake_print_label)
    monkeypatch.setattr(item_types_routes, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(items_routes, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(items_routes, "print_label", fake_print_label)
    monkeypatch.setattr(labels_routes, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(labels_routes, "print_label", fake_print_label)
    monkeypatch.setattr(labeling, "container_template_id", lambda: "container-test")
    monkeypatch.setattr(locations_routes, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(locations_routes, "print_label", fake_print_label)
    monkeypatch.setattr(locations_routes, "container_template_id", lambda: "container-test")

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
        json={"printer_id": "demo", "item_id": item["id"], "return_preview": True},
    )
    assert item_label.status_code == 200, item_label.text
    assert item_label.json()["status"] == "sent"
    assert item_label.json()["printer_id"] == "demo"
    assert item_label.json()["bytes_sent"] == 42
    assert print_calls[-1]["variables"]["serial"] == "L-1"
    assert print_calls[-1]["variables"]["internal_uuid"] == item["id"]

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
    assert location_label.status_code == 200, location_label.text
    assert print_calls[-1]["variables"]["container_name"] == "Shelf"
    assert print_calls[-1]["variables"]["internal_uuid"] == location["id"]

    location_override = label_client.post(
        "/v1/labels/print",
        json={
            "printer_id": "demo",
            "location_id": location["id"],
            "template_id": "container-test",
        },
    )
    assert location_override.status_code == 200, location_override.text
    assert print_calls[-1]["template"]["id"] == "container-test"


def test_label_print_on_create_item_and_location(label_client, monkeypatch):
    from thingdex import labeling
    from thingdex.routes import item_types as item_types_routes
    from thingdex.routes import items as items_routes
    from thingdex.routes import locations as locations_routes

    def fake_fetch_template(template_id: str):
        if template_id == "container-test":
            return {
                "template": {"id": template_id},
                "variables": [
                    {"name": "location_uuid", "mode": "required"},
                    {"name": "container_name", "mode": "required"},
                ],
            }
        return {
            "template": {"id": template_id},
            "variables": [{"name": "serial", "mode": "required"}],
        }

    def fake_print_label(*, printer_id, template, variables, return_preview=None, **kwargs):
        return {
            "printer_id": printer_id,
            "bytes_sent": 42,
            "preview_png_base64": "preview" if return_preview else None,
        }

    monkeypatch.setattr(labeling, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(labeling, "print_label", fake_print_label)
    monkeypatch.setattr(labeling, "container_template_id", lambda: "container-test")
    monkeypatch.setattr(item_types_routes, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(items_routes, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(items_routes, "print_label", fake_print_label)
    monkeypatch.setattr(locations_routes, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(locations_routes, "print_label", fake_print_label)
    monkeypatch.setattr(locations_routes, "container_template_id", lambda: "container-test")

    root = _get_root_location(label_client)
    item_type = _create_item_type(label_client, name="LabeledOnCreate")

    created_item = label_client.post(
        "/v1/items",
        json={
            "type_id": item_type["id"],
            "location_id": root["id"],
            "props": {"serial": "LC-1"},
            "label_print": {"printer_id": "demo", "return_preview": True},
        },
    )
    assert created_item.status_code == 200, created_item.text
    created_item_body = created_item.json()
    assert created_item_body["data"]["props"]["serial"] == "LC-1"
    assert created_item_body["side_effects"]["label_print"]["success"] is True

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
    created_location_body = created_location.json()
    assert created_location_body["data"]["name"] == "Drawer"
    assert created_location_body["side_effects"]["label_print"]["success"] is True


def test_label_print_failure_on_create_is_reported_without_rollback(label_client, monkeypatch):
    from thingdex import labeling
    from thingdex.labeling import LabelServiceError
    from thingdex.routes import item_types as item_types_routes
    from thingdex.routes import items as items_routes
    from thingdex.routes import locations as locations_routes

    def fake_fetch_template(template_id: str):
        if template_id == "container-test":
            return {
                "template": {"id": template_id},
                "variables": [
                    {"name": "location_uuid", "mode": "required"},
                    {"name": "container_name", "mode": "required"},
                ],
            }
        return {
            "template": {"id": template_id},
            "variables": [{"name": "serial", "mode": "required"}],
        }

    def failing_print_label(*, printer_id, template, variables, return_preview=None, **kwargs):
        raise LabelServiceError("Printer unavailable")

    monkeypatch.setattr(labeling, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(labeling, "container_template_id", lambda: "container-test")
    monkeypatch.setattr(item_types_routes, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(items_routes, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(items_routes, "print_label", failing_print_label)
    monkeypatch.setattr(locations_routes, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(locations_routes, "print_label", failing_print_label)
    monkeypatch.setattr(locations_routes, "container_template_id", lambda: "container-test")

    root = _get_root_location(label_client)
    item_type = _create_item_type(label_client, name="LabeledPrintFailure")

    created_item = label_client.post(
        "/v1/items",
        json={
            "type_id": item_type["id"],
            "location_id": root["id"],
            "props": {"serial": "FAIL-1"},
            "label_print": {"printer_id": "demo"},
        },
    )
    assert created_item.status_code == 200, created_item.text
    item_body = created_item.json()
    assert item_body["side_effects"]["label_print"] == {
        "requested": True,
        "success": False,
        "result": None,
        "error": "Printer unavailable",
    }
    assert label_client.get(f"/v1/items/{item_body['data']['id']}").status_code == 200

    created_location = label_client.post(
        "/v1/locations",
        json={
            "name": "Print Failure Shelf",
            "parent_id": root["id"],
            "kind": "shelf",
            "label_print": {"printer_id": "demo", "template_id": "container-test"},
        },
    )
    assert created_location.status_code == 200, created_location.text
    location_body = created_location.json()
    assert location_body["side_effects"]["label_print"] == {
        "requested": True,
        "success": False,
        "result": None,
        "error": "Printer unavailable",
    }
    assert label_client.get(f"/v1/locations/{location_body['data']['id']}").status_code == 200


def test_label_profiles_automatically_queue_new_item_and_location_labels(label_client, monkeypatch):
    from thingdex.routes import item_types as item_types_routes
    from thingdex.routes import items as items_routes
    from thingdex.routes import label_profiles as profile_routes
    from thingdex.routes import locations as locations_routes

    def fake_fetch_template(template_id: str):
        variables = (
            [{"name": "serial", "mode": "required"}]
            if template_id in {"item-auto", "item-test"}
            else [
                {"name": "location_uuid", "mode": "required"},
                {"name": "container_name", "mode": "required"},
            ]
        )
        return {"template": {"id": template_id}, "variables": variables}

    print_calls = []

    def fake_print_label(**kwargs):
        print_calls.append(kwargs)
        return {
            "status": "queued",
            "printer_id": kwargs["printer_id"],
            "bytes_sent": 42,
            "job_id": "job-test",
            "job_state": "queued",
        }

    monkeypatch.setattr(profile_routes, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(item_types_routes, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(items_routes, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(items_routes, "print_label", fake_print_label)
    monkeypatch.setattr(locations_routes, "fetch_template", fake_fetch_template)
    monkeypatch.setattr(locations_routes, "print_label", fake_print_label)

    root = _get_root_location(label_client)
    item_type = _create_item_type(label_client, name="AutoProfileType")
    item_profile = label_client.post(
        "/v1/label-profiles",
        json={
            "name": "Items",
            "entity_kind": "item",
            "item_type_id": item_type["id"],
            "template_id": "item-auto",
            "printer_id": "packing-desk",
        },
    )
    assert item_profile.status_code == 201, item_profile.text
    location_profile = label_client.post(
        "/v1/label-profiles",
        json={
            "name": "Containers",
            "entity_kind": "location",
            "location_kind": "container",
            "template_id": "location-auto",
            "printer_id": "warehouse",
        },
    )
    assert location_profile.status_code == 201, location_profile.text

    item = label_client.post(
        "/v1/items",
        json={"type_id": item_type["id"], "location_id": root["id"], "props": {"serial": "AUTO-1"}},
    )
    assert item.status_code == 200, item.text
    assert item.json()["side_effects"]["label_print"]["success"] is True
    assert print_calls[-1]["template_id"] == "item-auto"
    assert print_calls[-1]["idempotency_key"].startswith("thingdex:item:")

    location = label_client.post(
        "/v1/locations",
        json={"name": "Auto bin", "parent_id": root["id"], "kind": "container"},
    )
    assert location.status_code == 200, location.text
    assert location.json()["side_effects"]["label_print"]["success"] is True
    assert print_calls[-1]["template_id"] == "location-auto"
    assert print_calls[-1]["idempotency_key"].startswith("thingdex:location:")
