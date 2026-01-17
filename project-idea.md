# Household Inventory System – Engineering Specification

## 1. Purpose and Scope

This project is a self-hosted household inventory management system. It must allow a user to:

* Maintain a database of owned items (e.g., power supplies, 3D printing filament, resistors, bicycles, keys, etc.).
* Assign every item to a physical location in a nested location hierarchy (house → room → shelf → box → smaller box → compartment … with unlimited depth).
* Move items between locations by providing only the destination location ID (the system derives the full path automatically).
* Define arbitrary item types through a web UI (no DB migrations required when introducing new types/fields).
* Store type-specific properties for items (e.g., voltage/ampere for power supplies, color/diameter for filament).
* Perform complex searches across:

  * type,
  * location subtree (e.g., “anywhere under House X”),
  * properties,
  * in_use state (true/false),
  * and optionally historical measurements.
* Optionally track history per property (field-level “keep history” vs “overwrite current value” toggle per field).
* Store large “snapshot” payloads (e.g., `tree` output from a storage device scan) in a suitable way.

This system exposes a REST API that can be consumed by:

* a web frontend (admin + day-to-day UI),
* scripts (e.g., auto-updating free space of HDDs),
* QR/barcode scanning workflows (future-ready; not mandatory for v1).

The system is intended for a single household owner (single-tenant). Multi-user is not required for v1 but should not be made impossible by design.

---

## 2. Architectural Decisions

### 2.1 Database: PostgreSQL

PostgreSQL is the primary datastore.

### 2.2 Data Modeling Approach: “Relational Core + JSONB props + Schema-driven validation”

We do **not** use classic EAV (entity-attribute-value) tables. Instead:

* Common fields remain relational columns.
* Type-specific fields live in `items.props` as JSONB.
* Each item type defines a JSON schema-like configuration for validation and UI rendering.
* Per field, the type configuration can specify whether to track history.

This yields:

* simpler multi-attribute queries than EAV,
* fewer joins and fewer tables,
* flexible type/field creation via UI without migrations.

### 2.3 Locations: Recursive hierarchy (adjacency list)

All physical containers/areas are modeled as `locations` with `parent_id` pointing to another location. Depth is unlimited.

### 2.4 Item Relations: device/part usage

Item-to-item relations model installed/used parts. This supports:

* a device with many parts,
* "in use" vs "free in storage,"
* moving a device without re-scanning every part.

---

## 3. Core Concepts and Behavioral Rules

### 3.1 Locations

* A location represents any place/container where items can be placed.
* Examples: House, Room, Shelf, Cabinet, Box, Sub-box, Compartment.
* Locations are arbitrary, user-defined, and nestable to any depth.
* Items can be physically stored (location_id set) or installed/used by another item (location_id NULL).

**Moving an item**:

* Moving an item to another container requires only the destination location ID.
* The system must not require specifying the destination’s ancestors; those are already known in the location hierarchy.

### 3.2 Items

* An item is any physical object or group being tracked.
* Each item:

  * has a type (`type_id`),
  * has a physical location (`location_id`, nullable),
  * has a JSONB `props` map with type-specific values.
* Items have a `status` field (at minimum: `stored`, `in_use`, `broken`, `lost`, etc.). This is optional for searching and UI; 
### 3.3 Item Types and Fields (UI-driven)

Item types are created/edited via the web UI. Each type defines:

* Type name (unique).
* Field definitions:

  * key (machine-readable; used in `props`)
  * label (UI)
  * type (string, integer, number, boolean, date, date-time)
  * required flag
  * constraints (min/max, enum, regex pattern)
  * unit (optional; e.g., V, A, mm, GB)
  * default (optional)
  * `track_history` boolean (if enabled: store value changes in history table)
  * UI hints (group/ordering/helptext)

This allows:

* “Filament must always have color and diameter” (required fields)
* “HDD free space should keep a timeline” (`track_history = true` for `free_gb`)
* “Tree output should be stored as a snapshot rather than a frequently overwritten field” (see snapshots section)

### 3.4 Properties and History

Properties are stored in `items.props` as the current state.

If a field is configured with `track_history = true`, then on write/update the system must:

* update the current value in `items.props`
* and append an entry into `item_prop_history` with timestamp and the new value

This supports:

* current state queries (fast)
* history/time-series queries (when desired)

### 3.5 Large Snapshots (e.g., `tree` output)

Large text payloads (like filesystem trees) should not be stored as frequently rewritten property history fields if they are large and/or versioned. Instead:

* Store them as snapshot events in `item_snapshots`:

  * `kind` (e.g., `tree`)
  * `captured_at`
  * `data_text` (TEXT) or `data` (JSONB)
  * optional metadata (e.g., command args, host, exit code)

The current item may store only:

* `tree_snapshot_at` (in props)
* optionally a hash or reference to the latest snapshot

---

## 4. Database Schema (DDL)

### 4.1 Extensions

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

### 4.2 Tables

#### locations

```sql
CREATE TABLE locations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  parent_id uuid REFERENCES locations(id) ON DELETE CASCADE,
  kind text,
  meta jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX locations_parent_idx ON locations(parent_id);
```

#### item_types

```sql
CREATE TABLE item_types (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  schema jsonb NOT NULL DEFAULT '{}'::jsonb,
  ui jsonb NOT NULL DEFAULT '{}'::jsonb,
  label_template_id text
);
```

#### items

```sql
CREATE TABLE items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  type_id uuid NOT NULL REFERENCES item_types(id) ON DELETE RESTRICT,
  location_id uuid REFERENCES locations(id) ON DELETE RESTRICT,
  status text NOT NULL DEFAULT 'stored',
  props jsonb NOT NULL DEFAULT '{}'::jsonb,
  description text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX items_type_idx ON items(type_id);
CREATE INDEX items_location_idx ON items(location_id);
CREATE INDEX items_props_gin_idx ON items USING gin (props);
```

#### item_relations

```sql
CREATE TABLE item_relations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_item_id uuid NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  child_item_id uuid NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  relation_type text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  quantity integer,
  slot text,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX item_relations_parent_idx ON item_relations(parent_item_id);
CREATE INDEX item_relations_child_idx ON item_relations(child_item_id);
CREATE UNIQUE INDEX item_relations_unique_active
  ON item_relations(parent_item_id, child_item_id, relation_type)
  WHERE active = true;
```

#### item_prop_history

```sql
CREATE TABLE item_prop_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id uuid NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  prop_key text NOT NULL,
  captured_at timestamptz NOT NULL DEFAULT now(),
  value jsonb NOT NULL,
  source text
);

CREATE INDEX item_prop_history_item_key_time_idx
  ON item_prop_history(item_id, prop_key, captured_at DESC);
```

#### item_snapshots

```sql
CREATE TABLE item_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id uuid NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  kind text NOT NULL,
  captured_at timestamptz NOT NULL DEFAULT now(),
  data_text text,
  data jsonb,
  meta jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX item_snapshots_item_kind_time_idx
  ON item_snapshots(item_id, kind, captured_at DESC);
```

---

## 5. Type Schema Format (Contract)

The system uses a JSON document stored in `item_types.schema`. This is a project-defined schema (does not need to be full JSON Schema, but should be close enough for validation and UI generation).

### 5.1 Required Structure

```json
{
  "fields": {
    "field_key": {
      "type": "string|integer|number|boolean|date|date-time",
      "required": true|false,
      "default": <value>,
      "enum": [ ... ],
      "min": <number>,
      "max": <number>,
      "pattern": "<regex>",
      "track_history": true|false,
      "unit": "V|A|mm|GB|...",
      "label": "Human readable label",
      "help": "Help text for UI",
      "group": "UI group name",
      "order": 10
    }
  }
}
```

Validation rules:

* Every write to `items.props` must be validated against the type’s schema.
* Required fields must be present (at create time; updates may allow partial updates but must not end in an invalid state unless explicitly allowed).
* Types must match.
* Constraints (enum/min/max/pattern) must match.
* Unknown fields:

  * Either reject unknown keys, or accept them only if the type schema includes `"allow_additional": true`. Default: reject.

History behavior:

* On update, for each changed key with `track_history=true`, append `item_prop_history`.

Snapshots:

* For snapshot-like fields (e.g., tree output) do not store huge values in history; store in `item_snapshots`.

---

## 6. REST API Specification

The API is JSON over HTTP. Versioning prefix recommended: `/v1`.

### 6.1 Locations

#### Create location

`POST /v1/locations`

```json
{
  "name": "Box 7",
  "parent_id": "uuid-of-parent-location",
  "kind": "box",
  "meta": {}
}
```

#### Get location

`GET /v1/locations/{location_id}`

Returns location including parent info.

#### List children

`GET /v1/locations/{location_id}/children`

#### Get full path (for display)

`GET /v1/locations/{location_id}/path`

Returns array from root to this node:

```json
[
  {"id":"...","name":"House Main Street 123"},
  {"id":"...","name":"Basement"},
  {"id":"...","name":"Shelf 2"},
  {"id":"...","name":"Box A"}
]
```

#### List items in location (optional include descendants)

`GET /v1/locations/{location_id}/items?include_descendants=true`

This must support recursive subtree enumeration.

### 6.2 Item Types

#### Create type

`POST /v1/item-types`

```json
{
  "name": "storage_drive",
  "schema": { ... },
  "ui": { ... },
  "label_template_id": "text-center"
}
```

#### Update type

`PATCH /v1/item-types/{type_id}`
Allows updating schema/ui. Must consider backwards compatibility: existing items may become invalid; decide whether to:

* disallow schema changes that invalidate existing items, or
* allow and mark items as “invalid” until corrected. For v1, recommend: disallow invalidating changes.

#### List types

`GET /v1/item-types`

#### Get type

`GET /v1/item-types/{type_id}`

### 6.3 Items

#### Create item

`POST /v1/items`

```json
{
  "type": "storage_drive",
  "location_id": "uuid-location",
  "status": "stored",
  "description": "Backup disk",
  "props": {
    "capacity_gb": 4000,
    "serial": "XYZ...",
    "filesystem": "ext4"
  },
  "label_print": {
    "printer_id": "kuche-labelprinter-thermopapier-ente-zpl"
  }
}
```

Server:

* resolves `type` name to `type_id` (also allow `type_id` directly if desired)
* validates props against schema
* writes item

#### Update item metadata

`PATCH /v1/items/{item_id}`

```json
{
  "status": "in_use",
  "description": "..."
}
```

#### Merge props (partial update)

`PATCH /v1/items/{item_id}/props`

```json
{
  "free_gb": 812,
  "last_connected_at": "2025-12-23T19:12:00+01:00"
}
```

Server:

* validates each provided key/value
* merges into `items.props`
* for any changed key with `track_history=true`, append history record

#### Replace props (full overwrite)

`PUT /v1/items/{item_id}/props`

```json
{
  "capacity_gb": 4000,
  "free_gb": 812
}
```

Server:

* validates full object
* replaces props entirely
* history logic applies to changed fields

#### Move item

`PATCH /v1/items/{item_id}/move`

```json
{ "location_id": "uuid-new-location" }
```

Allowed only when the item is not installed/in use (no active relation).

#### Get item

`GET /v1/items/{item_id}`
Returns:

* item metadata
* effective location info (physical location id may be null; effective path resolves through parent device)
* type info (type name/id)
* props as JSON object

#### List items (basic)

`GET /v1/items?type=storage_drive&status=stored&in_use=false`

### 6.4 Item Relations

#### Attach part to device

`POST /v1/items/{item_id}/relations`

```json
{
  "child_item_id": "uuid-of-part",
  "relation_type": "installed_in|uses",
  "slot": "PCIe-1"
}
```

#### Detach part

`POST /v1/relations/{relation_id}/detach`

```json
{ "location_id": "uuid-location" }
```

#### List relations for item

* Children of a device: `GET /v1/items/{item_id}/relations/children`
* Parents of a part: `GET /v1/items/{item_id}/relations/parents`

### 6.5 History and Snapshots

#### Get property history

`GET /v1/items/{item_id}/history?prop_key=free_gb&limit=200`

#### Create snapshot

`POST /v1/items/{item_id}/snapshots`

```json
{
  "kind": "tree",
  "captured_at": "2025-12-23T19:13:10+01:00",
  "data_text": "<tree output>",
  "meta": { "cmd": "tree -a", "host": "server1" }
}
```

#### Get snapshots

`GET /v1/items/{item_id}/snapshots?kind=tree&limit=20`

### 6.6 Label Printing (optional, feature-flagged)

If `label_template_id` is set on an item type and the client provides `label_print` on item creation,
the backend renders the template and sends a print request to the printer service. Required template
variables must exist as item props.

Feature flag: `LABEL_PRINTING_ENABLED=true`.

---

## 7. Search API (Complex Queries)

Complex search should be implemented as a dedicated endpoint to avoid unmaintainable query-string combinatorics.

### Search endpoint

`POST /v1/items/search`

Request format:

```json
{
  "type": "power_supply",
  "location": {
    "root_location_id": "uuid-house",
    "include_descendants": true
  },
  "props_filters": [
    { "path": "voltage_v", "op": "==", "value": 9.0 },
    { "path": "current_a", "op": ">", "value": 2.0 }
  ],
  "in_use": false
}
```

Operators to support (minimum):

* `==`, `!=`
* `>`, `>=`, `<`, `<=` for numeric/date
* `contains` for strings (case-insensitive)
* `in` for enum sets

Server behavior:

* Resolve type name to `type_id`.
* Expand location subtree if `include_descendants=true` (recursive CTE).
* Apply JSONB filters.
* Apply availability filters via `EXISTS` / `NOT EXISTS` against `item_relations`.

Important: JSONB values should be stored in a consistent type format (numbers as JSON numbers, not strings) to avoid casting complexity. The API should enforce this.

---

## 8. Example Use Case: Storage Drive (HDD)

Required fields for `storage_drive` type likely include:

* `capacity_gb` (integer)
  Optional fields:
* `serial` (string)
* `filesystem` (string)
* `last_connected_at` (date-time, `track_history=true` if desired)
* `free_gb` (integer, `track_history=true`)
* For tree output:

  * Use `item_snapshots(kind='tree')`
  * Store last snapshot timestamp in props (`tree_snapshot_at`) if desired

---

## 9. Non-Functional Requirements

### 9.1 Validation

All item prop writes must be validated against the type schema:

* on create
* on props merge
* on props replace

### 9.2 Performance

* Indexing must be present:

  * `items(type_id)`
  * `items(location_id)`
  * GIN index on `items.props`
  * item_relations indexes
  * history/snapshot indexes
* Recursive subtree queries must be implemented with `WITH RECURSIVE`.
* For v1, adjacency list + recursive CTE is sufficient.

### 9.3 Auditability / History

* Field-level history is controlled by type schema `track_history`.
* Snapshot table stores potentially large payloads and supports multiple entries over time.

### 9.4 Deployment

* Docker-first is acceptable (API + Postgres).
* Provide a `.env`-based configuration.
* Provide a migration tool (Alembic recommended if using SQLAlchemy).
* Provide OpenAPI docs automatically (FastAPI).

---

## 10. Implementation Guidance (Recommended Stack)

* Backend: FastAPI + SQLAlchemy + Alembic
* Validation: Pydantic + custom validation against stored type schema (or JSONSchema library if adopting a strict JSON Schema dialect)
* DB: PostgreSQL 14+ recommended

---

## 11. Acceptance Criteria (Must-Haves for v1)

1. Create locations and nest them arbitrarily deep.
2. Create item types via API (UI will call same endpoints).
3. Create items of a type; props validated against type schema.
4. Move stored items by only updating `location_id`.
5. Store and retrieve current props.
6. Per-field history tracking based on type definition.
7. Store snapshots (tree output) and retrieve latest N.
8. Search endpoint that supports:

   * type filter,
   * location subtree filter,
   * multiple props filters with numeric comparisons,
   * in_use true/false filter.
9. Attach/detach parts to devices with item relations.
10. OpenAPI documentation is available and accurate.

---

## 12. Notes on Future Extensions (Not required in v1, but design must allow)

* QR label printing and scanning (items/locations have stable UUIDs).
* Multi-user auth/roles.
* Richer target modeling (devices/persons as first-class entities or items).
* `ltree` optimization for location subtree queries if needed.
