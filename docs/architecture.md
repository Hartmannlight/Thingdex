# Architecture

## Technology stack

| Layer | Technology | Responsibility |
| --- | --- | --- |
| HTTP | FastAPI | Routing, validation integration, OpenAPI generation |
| Contracts | Pydantic v2 | Request and response models |
| Persistence | SQLAlchemy 2 | Sessions, queries, recursive CTEs, transactions |
| Database | PostgreSQL 15+ | Durable state, JSONB, constraints, indexes, graph locks |
| Migrations | Alembic | Versioned database evolution |
| HTTP clients | HTTPX | Optional label and printer integrations |
| Runtime | Uvicorn | ASGI serving |
| Tests | pytest and FastAPI TestClient | PostgreSQL-backed integration coverage |

## Package structure

| Path | Purpose |
| --- | --- |
| `thingdex/main.py` | Application construction, lifecycle, and health endpoints |
| `thingdex/models.py` | SQLAlchemy tables, indexes, and database constraints |
| `thingdex/schemas.py` | Pydantic API contracts |
| `thingdex/validation.py` | Item-type schema and property validation |
| `thingdex/crud.py` | Shared recursive queries and domain helpers |
| `thingdex/routes/` | HTTP endpoints grouped by resource |
| `thingdex/labeling.py` | Template metadata compatibility client used by profile administration |
| `thingdex/print_intents.py` | Transactional outbox and idempotent PrintHub connector |
| `thingdex/print_worker.py` | Separately scalable outbox worker process |
| `alembic/` | Ordered database migrations |
| `openapi.json` | Committed external API contract |

## Request lifecycle

1. FastAPI validates the request with a Pydantic model.
2. A route dependency opens a SQLAlchemy session.
3. The route resolves referenced entities and checks domain invariants.
4. Item properties are validated against the stored item-type schema.
5. Inventory changes and any requested `PrintIntent` are committed atomically.
6. FastAPI serializes the declared response model.

The API process never contacts PrintHub while saving inventory. A separate
worker claims due outbox rows with `FOR UPDATE SKIP LOCKED`, leases each claim,
and submits the stable idempotency key. A worker crash can safely reclaim an
expired lease because PrintHub treats the submission as idempotent.

Database constraints duplicate the most important service checks so accidental
or concurrent writes cannot silently create invalid root locations or multiple
active in-use parents.

## Startup and health

The application lifespan verifies database access and creates the inventory
root if necessary. Schema creation is never performed by application code;
Alembic must be upgraded before Uvicorn starts.

- `/health/live` proves only that the API process can answer HTTP.
- `/health` and `/health/ready` query PostgreSQL and require the root location.

The container entrypoint runs `alembic upgrade head` before starting Uvicorn.
An external orchestrator should still wait for PostgreSQL readiness and use the
Thingdex readiness endpoint before routing traffic.

## API contract strategy

FastAPI generates the runtime OpenAPI document. `scripts/export_openapi.py`
writes that document to the committed `openapi.json`; CI fails when the two
drift. The generated SDK repository consumes this contract. Human-oriented
behavior and examples belong in this documentation rather than in a second,
manually maintained endpoint specification.
