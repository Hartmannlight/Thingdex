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


def _create_item(client, item_type_id, location_id, props):
    payload = {
        "type_id": item_type_id,
        "location_id": location_id,
        "props": props,
    }
    response = client.post("/v1/items", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _get_root_location(client):
    response = client.get("/v1/locations/root")
    assert response.status_code == 200, response.text
    return response.json()


def test_health_check_reports_root(client):
    response = client.get("/health")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "ok"
    assert data["root_location_id"]


def test_readiness_fails_closed_when_database_is_unavailable(client, monkeypatch):
    from thingdex import main

    def unavailable_session():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "SessionLocal", unavailable_session)

    assert client.get("/health/live").status_code == 200
    readiness = client.get("/health/ready")
    assert readiness.status_code == 503, readiness.text
    assert readiness.json()["detail"] == "Database unavailable"


def test_root_location_bootstrap_endpoint_is_idempotent(client):
    root = _get_root_location(client)

    bootstrapped = client.post("/v1/locations/root/bootstrap")
    assert bootstrapped.status_code == 200, bootstrapped.text
    assert bootstrapped.json()["id"] == root["id"]

    fetched = client.get("/v1/locations/root")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["id"] == root["id"]


def test_locations_tree_and_path(client):
    root = _get_root_location(client)
    response = client.post(
        "/v1/locations",
        json={"name": "Garage", "parent_id": root["id"], "kind": "room"},
    )
    assert response.status_code == 200, response.text
    child = response.json()["data"]

    path_response = client.get(f"/v1/locations/{child['id']}/path")
    assert path_response.status_code == 200, path_response.text
    path = path_response.json()
    assert [entry["id"] for entry in path] == [root["id"], child["id"]]

    children_response = client.get(f"/v1/locations/{root['id']}/children")
    assert children_response.status_code == 200, children_response.text
    children = children_response.json()
    assert any(entry["id"] == child["id"] for entry in children)

    tree_response = client.get("/v1/locations/tree")
    assert tree_response.status_code == 200, tree_response.text
    tree = tree_response.json()
    assert tree["id"] == root["id"]
    assert any(node["id"] == child["id"] for node in tree["children"])


def test_location_root_invariants(client):
    root = _get_root_location(client)

    orphan = client.post("/v1/locations", json={"name": "Disconnected", "kind": "room"})
    assert orphan.status_code == 400, orphan.text

    root_kind = client.patch(f"/v1/locations/{root['id']}", json={"kind": "room"})
    assert root_kind.status_code == 400, root_kind.text

    child = client.post(
        "/v1/locations",
        json={"name": "Room", "parent_id": root["id"], "kind": "room"},
    ).json()["data"]
    move_root = client.patch(f"/v1/locations/{root['id']}", json={"parent_id": child["id"]})
    assert move_root.status_code == 400, move_root.text

    promote_child = client.patch(f"/v1/locations/{child['id']}", json={"kind": "root"})
    assert promote_child.status_code == 400, promote_child.text


def test_item_type_item_and_history(client):
    root = _get_root_location(client)
    item_type = _create_item_type(client, name="Camera")
    item = _create_item(
        client,
        item_type_id=item_type["id"],
        location_id=root["id"],
        props={"serial": "ABC-123", "rating": 4.5},
    )

    detail_response = client.get(f"/v1/items/{item['id']}")
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["type"]["name"] == item_type["name"]

    update_response = client.patch(
        f"/v1/items/{item['id']}/props",
        json={"props": {"rating": 4.8}, "source": "test"},
    )
    assert update_response.status_code == 200, update_response.text

    history_response = client.get(f"/v1/items/{item['id']}/history")
    assert history_response.status_code == 200, history_response.text
    history = history_response.json()
    assert any(entry["prop_key"] == "rating" for entry in history)

    search_response = client.post(
        "/v1/items/search",
        json={
            "type": item_type["name"],
            "props_filters": [{"path": "serial", "op": "==", "value": "ABC-123"}],
        },
    )
    assert search_response.status_code == 200, search_response.text
    matches = search_response.json()
    assert any(entry["id"] == item["id"] for entry in matches)


def test_relations_detach_and_delete(client):
    root = _get_root_location(client)
    item_type = _create_item_type(client, name="Device")
    parent = _create_item(
        client,
        item_type_id=item_type["id"],
        location_id=root["id"],
        props={"serial": "PARENT-1", "rating": 3.5},
    )
    child = _create_item(
        client,
        item_type_id=item_type["id"],
        location_id=root["id"],
        props={"serial": "CHILD-1", "rating": 2.0},
    )

    relation_response = client.post(
        f"/v1/items/{parent['id']}/relations",
        json={"child_item_id": child["id"], "relation_type": "installed_in"},
    )
    assert relation_response.status_code == 200, relation_response.text
    relation = relation_response.json()

    child_detail = client.get(f"/v1/items/{child['id']}").json()
    assert child_detail["location"]["physical_location_id"] is None

    delete_response = client.delete(f"/v1/items/{child['id']}")
    assert delete_response.status_code == 409, delete_response.text

    detach_response = client.post(
        f"/v1/relations/{relation['id']}/detach",
        json={"location_id": root["id"]},
    )
    assert detach_response.status_code == 200, detach_response.text

    child_detail = client.get(f"/v1/items/{child['id']}").json()
    assert child_detail["location"]["physical_location_id"] == root["id"]

    delete_relation = client.delete(f"/v1/relations/{relation['id']}")
    assert delete_relation.status_code == 204, delete_relation.text

    delete_item = client.delete(f"/v1/items/{child['id']}")
    assert delete_item.status_code == 204, delete_item.text


def test_in_use_relations_reject_direct_state_changes_and_cycles(client):
    root = _get_root_location(client)
    item_type = _create_item_type(client, name="RelationInvariant")
    first = _create_item(
        client,
        item_type_id=item_type["id"],
        location_id=root["id"],
        props={"serial": "FIRST", "rating": 1.0},
    )
    second = _create_item(
        client,
        item_type_id=item_type["id"],
        location_id=root["id"],
        props={"serial": "SECOND", "rating": 1.0},
    )

    attached = client.post(
        f"/v1/items/{first['id']}/relations",
        json={"child_item_id": second["id"], "relation_type": "installed_in"},
    )
    assert attached.status_code == 200, attached.text

    direct_deactivate = client.patch(
        f"/v1/relations/{attached.json()['id']}",
        json={"active": False},
    )
    assert direct_deactivate.status_code == 422, direct_deactivate.text

    cycle = client.post(
        f"/v1/items/{second['id']}/relations",
        json={"child_item_id": first["id"], "relation_type": "uses"},
    )
    assert cycle.status_code == 409, cycle.text
    assert cycle.json()["detail"] == "Relation would create an in-use cycle"
