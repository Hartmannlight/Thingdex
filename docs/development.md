# Development

## Install tooling

```shell
poetry install --all-extras
```

The project keeps runtime dependencies separate from the `dev` and `docs`
extras, while `poetry.lock` makes all environments reproducible.

## Tests

```shell
poetry run pytest
```

Tests require PostgreSQL. `tests/conftest.py` creates an isolated database
schema for each fixture and drops it afterwards. Integration tests cover
locations, item types, items, search, history, snapshots, relations, health,
and label-side-effect behavior.

When PostgreSQL uses a non-default address:

```powershell
$env:THINGDEX_TEST_DATABASE_URL = "postgresql+psycopg://thingdex:password@127.0.0.1:5432/thingdex_test"
poetry run pytest
```

## Database changes

1. Update `thingdex/models.py`.
2. Add an Alembic revision under `alembic/versions/`.
3. Upgrade a real PostgreSQL database.
4. Run `poetry run alembic check` until no operations are detected.
5. Add migration and API regression tests.

Never use application startup to create tables. Startup may create the root
record only after migrations have established the schema.

## API contract changes

After changing routes or Pydantic models:

```shell
poetry run python scripts/export_openapi.py openapi.json
poetry run python scripts/check_openapi.py
```

Commit the updated `openapi.json` together with the implementation. Coordinate
breaking changes with the
[thingdex-sdk](https://github.com/Hartmannlight/thingdex-sdk) and UI consumers.

## Documentation

Preview locally:

```shell
poetry run mkdocs serve
```

Validate exactly as CI does:

```shell
poetry run mkdocs build --strict
```

Documentation rules:

- update an existing topical page instead of creating root-level notes;
- link to canonical documentation in other repositories instead of copying it;
- keep exact endpoint schemas in OpenAPI and explain workflows here;
- keep all environment variables in `configuration.md` and `.env.example`;
- use relative links within this documentation so local and hosted builds work.

Pushes to `main` that change documentation publish the static site through
`.github/workflows/docs.yml`. In the GitHub repository settings, Pages must use
**GitHub Actions** as its publishing source. The resulting canonical URL is
`https://hartmannlight.github.io/Thingdex/`.

## Quality gate

Before handing off a backend change, run:

```shell
poetry run pytest
poetry run alembic check
poetry run python scripts/check_openapi.py
poetry run mkdocs build --strict
git diff --check
```
