def _create_item_type(client, name="Widget"):
    payload = {
        "name": name,
        "schema": {
            "fields": {
                "serial": {"type": "string", "required": True},
                "rating": {"type": "number", "track_history": True},
            },
            "allow_additional": False,
        },
        "ui": {},
    }
    response = client.post("/v1/item-types", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _get_root_location(client):
    response = client.get("/v1/locations/root")
    assert response.status_code == 200, response.text
    return response.json()


def test_bulk_create_update_and_move(client):
    root = _get_root_location(client)
    item_type = _create_item_type(client, name="BulkType")

    bulk_create = client.post(
        "/v1/items/bulk",
        json={
            "items": [
                {"type_id": item_type["id"], "location_id": root["id"], "props": {"serial": "B1"}},
                {"type_id": item_type["id"], "location_id": root["id"], "props": {"serial": "B2"}},
            ]
        },
    )
    assert bulk_create.status_code == 200, bulk_create.text
    items = bulk_create.json()
    assert len(items) == 2

    bulk_update = client.patch(
        "/v1/items/bulk",
        json={
            "items": [
                {"id": items[0]["id"], "props": {"rating": 2.5}, "source": "bulk"},
                {"id": items[1]["id"], "description": "Updated"},
            ]
        },
    )
    assert bulk_update.status_code == 200, bulk_update.text

    history = client.get(f"/v1/items/{items[0]['id']}/history")
    assert history.status_code == 200, history.text
    assert any(entry["prop_key"] == "rating" for entry in history.json())

    new_location = client.post(
        "/v1/locations",
        json={"name": "Storage", "parent_id": root["id"], "kind": "room"},
    ).json()
    bulk_move = client.patch(
        "/v1/items/bulk/move",
        json={"item_ids": [items[0]["id"], items[1]["id"]], "location_id": new_location["id"]},
    )
    assert bulk_move.status_code == 200, bulk_move.text
    moved = bulk_move.json()
    assert all(entry["location_id"] == new_location["id"] for entry in moved)


def test_snapshots_create_list_delete(client):
    root = _get_root_location(client)
    item_type = _create_item_type(client, name="SnapshotType")
    item = client.post(
        "/v1/items",
        json={"type_id": item_type["id"], "location_id": root["id"], "props": {"serial": "S1"}},
    ).json()

    snapshot = client.post(
        f"/v1/items/{item['id']}/snapshots",
        json={
            "kind": "photo",
            "captured_at": "2026-01-01T12:00:00+00:00",
            "data_text": "preview",
            "meta": {"camera": "test"},
        },
    )
    assert snapshot.status_code == 200, snapshot.text
    snapshot_id = snapshot.json()["id"]

    listed = client.get(f"/v1/items/{item['id']}/snapshots")
    assert listed.status_code == 200, listed.text
    assert any(entry["id"] == snapshot_id for entry in listed.json())

    delete_resp = client.delete(f"/v1/items/{item['id']}/snapshots/{snapshot_id}")
    assert delete_resp.status_code == 204, delete_resp.text
