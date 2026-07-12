# Concepts and invariants

## Locations

A location represents a physical area or container: a home, room, cabinet,
shelf, box, drawer, or compartment. Locations form an adjacency-list tree.

Exactly one active location is the root. Every other location must have a
parent, and a location cannot be moved below one of its descendants. Deleting a
location soft-deletes its empty subtree; deletion is rejected while active
items remain anywhere below it.

## Item types

An item type defines the allowed shape of an item's `props` object. This gives
Thingdex a relational core without requiring a database migration whenever a
household introduces a new category.

Schema changes are validated against all active items of the type. A change is
rejected with HTTP `409` if it would invalidate existing inventory data. See
[Item type schema](reference/item-type-schema.md) for the complete dialect.

## Items

An item is a physical object or tracked group. It has:

- a stable UUID;
- an item type;
- a status and optional description;
- validated JSONB properties;
- either a physical location or an active in-use parent relation.

Items are soft-deleted. Active relations must be detached before an item can be
deleted.

## Relations and effective location

`installed_in` and `uses` model an item that is physically associated with a
parent item. Attaching such a child clears its direct `location_id`. Its
effective location is resolved by walking active parent relations until an
item with a physical location is found.

Thingdex enforces these rules:

- an item cannot be related to itself;
- an item has at most one active `installed_in` or `uses` parent;
- an in-use relation cannot introduce a graph cycle;
- graph mutations are serialized in PostgreSQL to prevent request races;
- active state cannot be patched directly;
- detaching the final in-use relation places the child at an explicit location
  or at the inventory root.

`paired_with` describes an association without changing either physical
location.

## Property history

Fields whose schema contains `track_history: true` produce an
`item_prop_history` record whenever their value changes through a property
update. The item retains the current value in `props`; history is an event log,
not the source used for ordinary reads.

## Snapshots

Snapshots store larger or independently versioned observations such as a
filesystem tree, diagnostic output, or structured scan. A snapshot has a kind,
capture time, optional text, optional JSON data, and metadata.

Use properties for current searchable facts, property history for small value
changes, and snapshots for larger observations.
