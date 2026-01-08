# API Documentation (Thingdex)

This document complements the generated OpenAPI spec (`openapi.json`) and the
interactive docs at `/docs`. It summarizes how to use the API in practice.

## Base URLs
- API: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`
- Health: `GET /health` returns `root_location_id` when available.

## Root Location Name
- Default root name is `World`.
- Override with `ROOT_LOCATION_NAME` environment variable before starting the API.

## Core Workflow
1) Create a root location (`POST /v1/locations`).
2) Create item types with schema definitions (`POST /v1/item-types`).
3) Create items with validated props (`POST /v1/items`).
4) Use `PATCH /v1/items/{id}/props` for incremental updates and history.
5) Alternatively, call `GET /v1/locations/root` to auto-create and fetch the root.

## Locations
- Create: `POST /v1/locations`
- Root (idempotent): `GET /v1/locations/root`
- Get: `GET /v1/locations/{id}`
- Update/move: `PATCH /v1/locations/{id}` (set `parent_id` to move)
- Children: `GET /v1/locations/{id}/children`
- Path: `GET /v1/locations/{id}/path`
- Items in location: `GET /v1/locations/{id}/items?include_descendants=true`

Location create notes:
- Optional label print (feature-flagged):
  ```json
  {
    "label_print": {
      "printer_id": "kuche-labelprinter-thermopapier-ente-zpl",
      "return_preview": false
    }
  }
  ```
  Requires `LABEL_PRINTING_ENABLED=true` on the backend.

## Item Types
- Create: `POST /v1/item-types`
- List: `GET /v1/item-types`
- Get: `GET /v1/item-types/{id}`
- Update: `PATCH /v1/item-types/{id}`
- Optional: `label_template_id` links to label template IDs from
  `http://label.xn--jahnstrae-n1a.de/api/v1/templates`.
  Required template variables must exist as required fields in the item type schema.

## Items
- Create: `POST /v1/items`
- Get: `GET /v1/items/{id}`
- List: `GET /v1/items?type=...&status=...&in_use=...`
- Move: `PATCH /v1/items/{id}/move` (only if not in use)
- Update metadata: `PATCH /v1/items/{id}`
- Merge props: `PATCH /v1/items/{id}/props`
- Replace props: `PUT /v1/items/{id}/props`
- History: `GET /v1/items/{id}/history?prop_key=free_gb`
- Snapshots: `POST /v1/items/{id}/snapshots` and `GET /v1/items/{id}/snapshots`
- Attach part: `POST /v1/items/{id}/relations`
- List parts: `GET /v1/items/{id}/relations/children`
- List parents: `GET /v1/items/{id}/relations/parents`

Item detail includes effective location:
```json
{
  "location": {
    "physical_location_id": "uuid-or-null",
    "effective_location_id": "uuid-or-null",
    "effective_location_path": [
      {"id": "uuid", "name": "World"},
      {"id": "uuid", "name": "Room"}
    ]
  }
}
```

Item create notes:
- `location_id` is required for physically stored items.
- Items attached to a device have `location_id: null` and are linked via relations.
- Optional label print (feature-flagged):
  ```json
  {
    "label_print": {
      "printer_id": "kuche-labelprinter-thermopapier-ente-zpl",
      "return_preview": false
    }
  }
  ```
  Requires `LABEL_PRINTING_ENABLED=true` on the backend.

## Relations
- Detach: `POST /v1/relations/{relation_id}/detach`
- Deactivate: `PATCH /v1/relations/{relation_id}`
- Relation types: `installed_in`, `uses`, `paired_with`

## Labels
- Reprint by item or location: `POST /v1/labels/print`

```json
{
  "printer_id": "kuche-labelprinter-thermopapier-ente-zpl",
  "item_id": "uuid-item"
}
```
Requires a label template on the item type (`label_template_id`).

```json
{
  "printer_id": "kuche-labelprinter-thermopapier-ente-zpl",
  "location_id": "uuid-location"
}
```
Requires `location.meta.label_template_id` to be set.

## Search
Use a dedicated search endpoint to avoid combinatorial query strings.

Example:
```json
POST /v1/items/search
{
  "type": "storage_drive",
  "location": { "root_location_id": "uuid", "include_descendants": true },
  "props_filters": [
    { "path": "free_gb", "op": ">", "value": 600 }
  ],
  "in_use": false
}
```

## Example: Create Type + Item
```json
POST /v1/item-types
{
  "name": "storage_drive",
  "schema": {
    "fields": {
      "capacity_gb": { "type": "integer", "required": true },
      "free_gb": { "type": "integer", "track_history": true }
    }
  }
}
```

```json
POST /v1/items
{
  "type": "storage_drive",
  "location_id": "uuid-location",
  "props": { "capacity_gb": 4000, "free_gb": 812 }
}
```
