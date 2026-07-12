# Getting started

## Prerequisites

- Python 3.13 or newer
- Poetry 2.x
- PostgreSQL 15 or newer

Thingdex uses PostgreSQL-specific UUID, JSONB, recursive CTE, partial-index,
and advisory-lock features. SQLite is not a supported substitute.

## Install

```shell
git clone https://github.com/Hartmannlight/Thingdex.git
cd Thingdex
poetry install --all-extras
```

The `dev` extra installs test tooling and the `docs` extra installs Material
for MkDocs. Poetry records exact resolved versions in `poetry.lock`.

## Configure PostgreSQL

Create a database and user using your normal PostgreSQL administration tools.
Then expose the connection URL to both Alembic and the application.

PowerShell:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://thingdex:password@127.0.0.1:5432/thingdex"
```

Bash:

```bash
export DATABASE_URL="postgresql+psycopg://thingdex:password@127.0.0.1:5432/thingdex"
```

The repository's `.env.example` is a configuration reference. Thingdex does
not load `.env` files itself; a process manager, container runtime, or shell
must provide the variables.

## Initialize and run

```shell
poetry run alembic upgrade head
poetry run uvicorn thingdex.main:app --reload
```

Application startup creates the one root location when it does not exist. The
name is controlled by `ROOT_LOCATION_NAME` only for that first creation.

Open these endpoints:

- API documentation: `http://127.0.0.1:8000/docs`
- Alternative API reference: `http://127.0.0.1:8000/redoc`
- Readiness: `http://127.0.0.1:8000/health/ready`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

## Create the first inventory records

Fetch the automatically created root:

```shell
curl http://127.0.0.1:8000/v1/locations/root
```

Create an item type:

```json
POST /v1/item-types
{
  "name": "storage_box",
  "schema": {
    "fields": {
      "color": {"type": "string"},
      "label": {"type": "string", "required": true}
    },
    "allow_additional": false
  },
  "ui": {"icon": "archive-box"}
}
```

Create a child location below the root, then create an item using the returned
type and location UUIDs. The interactive API documentation is the quickest way
to explore the complete request and response models.

## Verify the checkout

```shell
poetry run pytest
poetry run alembic check
poetry run python scripts/check_openapi.py
poetry run mkdocs build --strict
```
