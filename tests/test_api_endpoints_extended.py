def _create_item_type(client, name="Widget", schema=None, label_template_id=None):
    if schema is None:
        schema = {
            "fields": {
                "serial": {"type": "string", "required": True},
                "rating": {"type": "number", "track_history": True},
            },
            "allow_additional": False,
        }
    payload = {
        "name": name,
        "schema": schema,
        "ui": {"icon": "box"},
        "label_template_id": label_template_id,
    }
    response = client.post("/v1/item-types", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _create_item(client, item_type_id, location_id, props, status=None, description=None):
    payload = {
        "type_id": item_type_id,
        "location_id": location_id,
        "props": props,
        "status": status,
        "description": description,
    }
    response = client.post("/v1/items", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _get_root_location(client):
    response = client.get("/v1/locations/root")
    assert response.status_code == 200, response.text
    return response.json()


def test_item_type_list_get_update_delete(client):
    item_type = _create_item_type(client, name="TypeA")

    listed = client.get("/v1/item-types")
    assert listed.status_code == 200, listed.text
    assert any(entry["id"] == item_type["id"] for entry in listed.json())

    fetched = client.get(f"/v1/item-types/{item_type['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["name"] == "TypeA"

    updated = client.patch(
        f"/v1/item-types/{item_type['id']}",
        json={"name": "TypeA2", "ui": {"icon": "crate"}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "TypeA2"
    assert updated.json()["ui"]["icon"] == "crate"

    deleted = client.delete(f"/v1/item-types/{item_type['id']}")
    assert deleted.status_code == 204, deleted.text

    missing = client.get(f"/v1/item-types/{item_type['id']}")
    assert missing.status_code == 404, missing.text


def test_item_type_delete_conflict_when_items_exist(client):
    root = _get_root_location(client)
    item_type = _create_item_type(client, name="TypeB")
    _create_item(client, item_type["id"], root["id"], {"serial": "T-1", "rating": 1.0})

    deleted = client.delete(f"/v1/item-types/{item_type['id']}")
    assert deleted.status_code == 409, deleted.text


def test_items_list_update_move_delete_and_missing_location(client):
    root = _get_root_location(client)
    alt_location = client.post(
        "/v1/locations",
        json={"name": "Bin", "parent_id": root["id"], "kind": "container"},
    ).json()["data"]
    item_type = _create_item_type(client, name="TypeC")
    item = _create_item(
        client,
        item_type["id"],
        root["id"],
        {"serial": "C-1", "rating": 2.5},
        status="stored",
        description="Stored item",
    )

    listed = client.get(f"/v1/items?type={item_type['name']}")
    assert listed.status_code == 200, listed.text
    assert any(entry["id"] == item["id"] for entry in listed.json())

    updated = client.patch(
        f"/v1/items/{item['id']}",
        json={"status": "lost", "description": "Missing"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "lost"
    assert updated.json()["description"] == "Missing"

    moved = client.patch(
        f"/v1/items/{item['id']}/move",
        json={"location_id": alt_location["id"]},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["location_id"] == alt_location["id"]

    deleted = client.delete(f"/v1/items/{item['id']}")
    assert deleted.status_code == 204, deleted.text

    missing = client.get(f"/v1/items/{item['id']}")
    assert missing.status_code == 404, missing.text

    listed_deleted = client.get("/v1/items?include_deleted=true")
    assert listed_deleted.status_code == 200, listed_deleted.text
    assert any(entry["id"] == item["id"] for entry in listed_deleted.json())

    # Force a missing-location case and verify endpoint response.
    orphan = _create_item(client, item_type["id"], root["id"], {"serial": "C-2", "rating": 1.0})
    from thingdex.db import SessionLocal
    from thingdex.models import Item
    with SessionLocal() as db:
        db.query(Item).filter(Item.id == orphan["id"]).update({"location_id": None})
        db.commit()
    missing_location = client.get("/v1/items/missing-location")
    assert missing_location.status_code == 200, missing_location.text
    assert any(entry["id"] == orphan["id"] for entry in missing_location.json())


def test_item_props_replace_applies_defaults(client):
    root = _get_root_location(client)
    schema = {
        "fields": {
            "serial": {"type": "string", "required": True},
            "color": {"type": "string", "default": "black"},
        },
        "allow_additional": False,
    }
    item_type = _create_item_type(client, name="TypeDefaults", schema=schema)
    item = _create_item(client, item_type["id"], root["id"], {"serial": "D-1"})

    replaced = client.put(
        f"/v1/items/{item['id']}/props",
        json={"props": {"serial": "D-1"}, "source": "replace"},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["props"]["color"] == "black"


def test_relations_list_update_detach_delete_and_in_use_filter(client):
    root = _get_root_location(client)
    item_type = _create_item_type(client, name="TypeRel")
    parent = _create_item(client, item_type["id"], root["id"], {"serial": "P-1", "rating": 1.0})
    child = _create_item(client, item_type["id"], root["id"], {"serial": "C-1", "rating": 1.0})

    relation = client.post(
        f"/v1/items/{parent['id']}/relations",
        json={"child_item_id": child["id"], "relation_type": "installed_in", "quantity": 1},
    )
    assert relation.status_code == 200, relation.text
    relation_id = relation.json()["id"]

    children = client.get(f"/v1/items/{parent['id']}/relations/children")
    assert children.status_code == 200, children.text
    assert any(entry["id"] == relation_id for entry in children.json())

    parents = client.get(f"/v1/items/{child['id']}/relations/parents")
    assert parents.status_code == 200, parents.text
    assert any(entry["id"] == relation_id for entry in parents.json())

    in_use = client.get("/v1/items?in_use=true")
    assert in_use.status_code == 200, in_use.text
    assert any(entry["id"] == child["id"] for entry in in_use.json())

    updated = client.patch(
        f"/v1/relations/{relation_id}",
        json={"quantity": 2, "slot": "A1", "notes": "Updated"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["quantity"] == 2
    assert updated.json()["slot"] == "A1"

    delete_blocked = client.delete(f"/v1/relations/{relation_id}")
    assert delete_blocked.status_code == 409, delete_blocked.text

    detached = client.post(
        f"/v1/relations/{relation_id}/detach",
        json={"location_id": root["id"]},
    )
    assert detached.status_code == 200, detached.text

    deleted = client.delete(f"/v1/relations/{relation_id}")
    assert deleted.status_code == 204, deleted.text


def test_locations_update_delete_conflict(client):
    root = _get_root_location(client)
    location = client.post(
        "/v1/locations",
        json={"name": "Shelf", "parent_id": root["id"], "kind": "shelf"},
    ).json()["data"]
    updated = client.patch(
        f"/v1/locations/{location['id']}",
        json={"name": "Shelf-1", "kind": "container", "meta": {"label": "A"}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Shelf-1"
    fetched = client.get(f"/v1/locations/{location['id']}")
    assert fetched.status_code == 200, fetched.text

    item_type = _create_item_type(client, name="TypeLoc")
    stored = _create_item(client, item_type["id"], location["id"], {"serial": "L-1", "rating": 1.0})
    listed = client.get(f"/v1/locations/{location['id']}/items")
    assert listed.status_code == 200, listed.text
    assert any(entry["id"] == stored["id"] for entry in listed.json())
    blocked = client.delete(f"/v1/locations/{location['id']}")
    assert blocked.status_code == 409, blocked.text

    deleted_item = client.delete(f"/v1/items/{stored['id']}")
    assert deleted_item.status_code == 204, deleted_item.text
    deleted_location = client.delete(f"/v1/locations/{location['id']}")
    assert deleted_location.status_code == 204, deleted_location.text
    missing_location = client.get(f"/v1/locations/{location['id']}")
    assert missing_location.status_code == 404, missing_location.text
