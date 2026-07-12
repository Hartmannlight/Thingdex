# Thingdex backend

Thingdex is the inventory data service for the Thingdex ecosystem. It answers
three practical questions:

1. What objects exist?
2. Where are they physically or effectively located?
3. What structured facts and history are known about them?

The service exposes a JSON REST API, persists data in PostgreSQL, and publishes
an OpenAPI contract for user interfaces, generated clients, and automation.

## Repository boundary

This repository owns:

- the FastAPI application and HTTP contract;
- inventory-domain rules and validation;
- the PostgreSQL data model and Alembic migrations;
- the backend container image;
- backend tests and documentation.

It does not own the web interface, TypeScript SDK, label editor, printer
gateway, or multi-service deployment. See [Integrations](integrations.md) for
the repositories that provide those pieces.

## Capabilities

| Area | Capability |
| --- | --- |
| Locations | An arbitrarily deep tree with exactly one protected root |
| Item types | User-defined property schemas and UI metadata |
| Items | Structured JSONB properties, status, description, and physical location |
| Relations | Installed, used, or paired items with safe attach/detach transitions |
| Effective location | Parts inherit a location through their active parent chain |
| History | Selected property changes are recorded as append-only events |
| Snapshots | Larger text or JSON observations can be stored independently |
| Search | Type, location subtree, property, and in-use filters |
| Labels | Optional integration with template and printer services |

## Where to continue

- [Getting started](getting-started.md) — run a development instance.
- [Concepts](concepts.md) — understand the inventory model.
- [API](api.md) — use and evolve the HTTP contract.
- [Configuration](configuration.md) — review every environment variable.
- [Deployment](deployment.md) — run the production image safely.
