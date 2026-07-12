# Thingdex

Thingdex is the backend and source of truth for a self-hosted household
inventory. It stores physical locations, user-defined item types, inventory
items, tracked property history, snapshots, and relations between items such
as installed or used components.

This repository contains only the backend service. User interfaces, generated
SDKs, label tooling, and deployment orchestration live in separate repositories.

## What it provides

- A versioned FastAPI REST API with an exported OpenAPI contract.
- Nested physical locations with one protected root location.
- Schema-driven item types backed by flexible PostgreSQL JSONB properties.
- Atomic attach/detach workflows and effective-location resolution for parts.
- Optional property history, large snapshots, search, and label printing.
- Alembic migrations, health endpoints, a production container, and tests.

## Documentation

The complete documentation lives in [`docs/`](docs/index.md) and is built with
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/).

```shell
poetry install --all-extras
poetry run mkdocs serve
```

Build the same strict static site used by CI:

```shell
poetry run mkdocs build --strict
```

Start with the [getting-started guide](docs/getting-started.md), review all
[configuration variables](docs/configuration.md), or read the
[architecture](docs/architecture.md).

## Quick development start

Thingdex requires Python 3.13+ and PostgreSQL 15+.

```shell
poetry install --all-extras
poetry run alembic upgrade head
poetry run uvicorn thingdex.main:app --reload
```

Set `DATABASE_URL` before migrating when PostgreSQL is not available at the
local default. The interactive API is exposed at `http://127.0.0.1:8000/docs`.

```shell
poetry run pytest
poetry run alembic check
poetry run python scripts/check_openapi.py
```

## Related repositories

- [Thingdex Home Inventory](https://github.com/Hartmannlight/Thingdex-Home-Inventory) — system-level documentation and deployment
- [ThingdexUI](https://github.com/Hartmannlight/ThingdexUI) — browser UI
- [thingdex-sdk](https://github.com/Hartmannlight/thingdex-sdk) — generated TypeScript client
- [PrintHub-ZPL-II](https://github.com/Hartmannlight/PrintHub-ZPL-ll) — label rendering and printer gateway

## License

No license has been published for this repository yet.
