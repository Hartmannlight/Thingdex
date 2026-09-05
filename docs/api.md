# API guide

All inventory resources use the `/v1` prefix. Health and OpenAPI endpoints are
unversioned operational endpoints.

## Canonical references

- Runtime Swagger UI: `/docs`
- Runtime ReDoc: `/redoc`
- Runtime contract: `/openapi.json`
- Repository contract: `openapi.json`
- TypeScript client: [thingdex-sdk](https://github.com/Hartmannlight/thingdex-sdk)

The generated OpenAPI document is authoritative for exact payload and response
shapes. This page explains workflows and semantics.

## Locations

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/v1/locations/root` | Fetch the unique root |
| `POST` | `/v1/locations/root/bootstrap` | Idempotently ensure the root exists |
| `POST` | `/v1/locations` | Create a child location |
| `GET` | `/v1/locations/tree` | Return a nested location tree |
| `GET` | `/v1/locations/{id}` | Fetch one location |
| `PATCH` | `/v1/locations/{id}` | Rename, edit metadata, or move a location |
| `GET` | `/v1/locations/{id}/children` | List direct children |
| `GET` | `/v1/locations/{id}/path` | Resolve root-to-location breadcrumbs |
| `GET` | `/v1/locations/{id}/items` | List directly or recursively stored items |
| `DELETE` | `/v1/locations/{id}` | Soft-delete an empty non-root subtree |

Non-root creation requires `parent_id`. The root cannot be moved, retyped, or
deleted.

## Item types

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/item-types` | Create a schema-driven type |
| `GET` | `/v1/item-types` | List types |
| `GET` | `/v1/item-types/{id}` | Fetch a type |
| `PATCH` | `/v1/item-types/{id}` | Update name, schema, UI hints, or label template |
| `DELETE` | `/v1/item-types/{id}` | Soft-delete an unused type |

Invalid schemas return `400`. Schema changes that would invalidate existing
items return `409` with affected item IDs and validation errors.

## Items

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/items` | Create an item |
| `POST` | `/v1/items/bulk` | Atomically create several items |
| `PATCH` | `/v1/items/bulk` | Atomically update several items |
| `PATCH` | `/v1/items/bulk/move` | Atomically move several stored items |
| `GET` | `/v1/items` | List by type, status, or in-use state |
| `POST` | `/v1/items/search` | Apply compound inventory filters |
| `GET` | `/v1/items/missing-location` | Find items without an effective location |
| `GET` | `/v1/items/{id}` | Fetch enriched item details |
| `PATCH` | `/v1/items/{id}` | Update status or description |
| `PATCH` | `/v1/items/{id}/move` | Move a stored item |
| `PATCH` | `/v1/items/{id}/props` | Merge validated properties |
| `PUT` | `/v1/items/{id}/props` | Replace the complete property object |
| `DELETE` | `/v1/items/{id}` | Soft-delete an unrelated item |

Create and bulk operations are transactional for their database writes. A
requested label print creates a `PrintIntent` in the same transaction as the
inventory record. The response reports `queued` as soon as both are durable;
availability of PrintHub cannot roll back or delay the inventory request.

Authenticated operators can inspect `GET /v1/print-intents`, fetch one intent,
or retry a terminally failed intent. These responses deliberately omit the
resolved variable snapshot. All endpoints require `THINGDEX_PRINT_ADMIN_TOKEN`
and fail closed when it is unset.

`POST /v1/integrations/printhub/events` accepts HMAC-signed status events.
Event IDs are idempotent and a monotonically increasing sequence prevents an
older replay from rolling back the visible PrintHub job state.

## Relations

Attach a child through `POST /v1/items/{parent_id}/relations`. List outgoing or
incoming relations through the parent's `children` and child's `parents`
endpoints.

Relation metadata can be changed with `PATCH /v1/relations/{id}`. Active state
cannot be patched. Use `POST /v1/relations/{id}/detach` to deactivate an in-use
relation and place the child at a physical location. An inactive relation can
then be soft-deleted with `DELETE /v1/relations/{id}`.

## History and snapshots

- `GET /v1/items/{id}/history` lists tracked property events.
- `POST /v1/items/{id}/snapshots` creates a snapshot.
- `GET /v1/items/{id}/snapshots` lists snapshots by time and optional kind.
- `DELETE /v1/items/{id}/snapshots/{snapshot_id}` soft-deletes a snapshot.

## Search

```json
{
  "type": "storage_drive",
  "location": {
    "root_location_id": "018f0000-0000-7000-8000-000000000001",
    "include_descendants": true
  },
  "props_filters": [
    {"path": "capacity_gb", "op": ">=", "value": 4000},
    {"path": "interface", "op": "in", "value": ["sata", "sas"]}
  ],
  "in_use": false
}
```

Supported property operators are `==`, `!=`, `>`, `>=`, `<`, `<=`,
`contains`, and `in`. Store numbers as JSON numbers and ISO dates as strings so
PostgreSQL casts remain consistent.

## Errors and soft-deleted resources

| Status | Meaning |
| --- | --- |
| `400` | Invalid domain request or property schema |
| `404` | Resource does not exist or is soft-deleted |
| `409` | Operation conflicts with an inventory invariant |
| `422` | Pydantic request-shape validation failed |
| `502` | Optional label or printer service failed |
| `503` | Readiness dependency is unavailable |

Administrative list endpoints expose `include_deleted` where historical rows
must be inspected. Ordinary reads hide soft-deleted data.
