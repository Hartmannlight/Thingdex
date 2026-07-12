# Data model

The Alembic migrations are the authoritative database definition. SQLAlchemy
metadata mirrors the same tables, constraints, and indexes so `alembic check`
can detect drift.

## Tables

### `locations`

Stores the adjacency-list physical location tree.

| Column | Meaning |
| --- | --- |
| `id` | UUID primary key |
| `name` | Display name |
| `parent_id` | Parent location; null only for the root |
| `kind` | Optional category; `root` is reserved for the root |
| `meta` | Free-form JSONB metadata |
| `deleted_at` | Soft-deletion timestamp |

A check constraint enforces the root shape, and a partial unique index permits
only one root.

### `item_types`

Stores the type name, validation schema, UI hints, optional label-template ID,
and soft-deletion timestamp. Type names are globally unique, including
soft-deleted rows.

### `items`

Stores the type reference, optional physical location, status, description,
current JSONB properties, creation/update timestamps, and soft-deletion
timestamp. Foreign keys restrict deletion of referenced types and locations.

Indexes support type filtering, physical-location filtering, and JSONB access.

### `item_relations`

Stores directed parent-to-child relations with type, active state, quantity,
slot, notes, creation time, and soft-deletion timestamp.

Constraints prevent self-relations and non-positive quantities. Partial unique
indexes prevent duplicate active edges and more than one active in-use parent
per child. Application-level cycle detection and a PostgreSQL advisory
transaction lock protect graph-wide invariants.

### `item_prop_history`

Stores item ID, property key, capture time, JSONB value, source, and
soft-deletion timestamp. The composite index supports newest-first history
queries for one item and property.

### `item_snapshots`

Stores item ID, kind, capture time, optional text, optional JSONB data,
metadata, and soft-deletion timestamp. The composite index supports recent
snapshot queries by item and kind.

## Soft deletion

Ordinary queries filter `deleted_at IS NULL`. Soft deletion preserves UUIDs and
historical records but does not make unique names reusable. The API exposes
`include_deleted` only on selected administrative list operations.

## Recursive queries

Recursive CTEs provide:

- location descendants;
- root-to-location paths;
- cycle checks for relation graph changes.

Effective item location is resolved iteratively through the active in-use
parent chain, with cycle protection as a defensive fallback.

## Migration history

| Revision | Change |
| --- | --- |
| `0001_initial` | Initial inventory tables and indexes |
| `0002_root_location_unique` | Unique root marker and index |
| `0003_drop_item_name` | Removed duplicated item name |
| `0004_item_relations` | Added part relations and nullable item locations |
| `0005_label_template_id` | Linked item types to label templates |
| `0006_soft_delete` | Added soft-deletion timestamps |
| `0007_inventory_invariants` | Enforced root and active-relation integrity |
