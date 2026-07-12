# Repository Guidelines

## Scope

This repository owns the Thingdex FastAPI backend, its PostgreSQL schema,
Alembic migrations, OpenAPI contract, production image, and backend
documentation. UI, SDK generation, label services, and multi-service
orchestration belong to their respective repositories.

## Development

- Install all tooling with `poetry install --all-extras`.
- Run tests with `poetry run pytest` against PostgreSQL.
- Verify migrations with `poetry run alembic check`.
- Verify the API contract with `poetry run python scripts/check_openapi.py`.
- Build documentation with `poetry run mkdocs build --strict`.

## Structure

- `thingdex/`: application code and API routes.
- `alembic/`: database migrations.
- `tests/`: PostgreSQL-backed integration tests.
- `docs/`: canonical human-readable documentation.
- `openapi.json`: committed machine-readable API contract.

## Change rules

- Preserve the root-location, relation-graph, and schema-compatibility invariants.
- Add a migration for every persistent schema change.
- Add regression tests for behavior changes.
- Regenerate `openapi.json` after API contract changes.
- Update the relevant page under `docs/`; do not add standalone root-level design notes.
