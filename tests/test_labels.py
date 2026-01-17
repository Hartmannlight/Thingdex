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

    def fake_print_label(*, printer_id, template, variables, return_preview=None):
        return {
            "printer_id": printer_id,
            "template": template,
            "variables": variables,
            "return_preview": return_preview,
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
    ).json()

    item_label = label_client.post(
        "/v1/labels/print",
        json={"printer_id": "demo", "item_id": item["id"], "return_preview": True},
    )
    assert item_label.status_code == 200, item_label.text
    assert item_label.json()["variables"]["serial"] == "L-1"
    assert item_label.json()["variables"]["internal_uuid"] == item["id"]

    location = label_client.post(
        "/v1/locations",
        json={
            "name": "Shelf",
            "parent_id": root["id"],
            "kind": "shelf",
            "meta": {"label_template_id": "container-test"},
        },
    ).json()
    location_label = label_client.post(
        "/v1/labels/print",
        json={"printer_id": "demo", "location_id": location["id"]},
    )
    assert location_label.status_code == 200, location_label.text
    assert location_label.json()["variables"]["container_name"] == "Shelf"
    assert location_label.json()["variables"]["internal_uuid"] == location["id"]

    location_override = label_client.post(
        "/v1/labels/print",
        json={
            "printer_id": "demo",
            "location_id": location["id"],
            "template_id": "container-test",
        },
    )
    assert location_override.status_code == 200, location_override.text
    assert location_override.json()["template"]["id"] == "container-test"


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

    def fake_print_label(*, printer_id, template, variables, return_preview=None):
        return {
            "printer_id": printer_id,
            "template": template,
            "variables": variables,
            "return_preview": return_preview,
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
