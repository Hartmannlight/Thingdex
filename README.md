# Thingdex

Backend API for the household inventory system described in `project-idea.md`.

## Quick Start (Local API + Docker Postgres)
1. Start Postgres:
   `docker compose up -d`
2. Install dependencies:
   `poetry install`
3. Run migrations:
   `poetry run alembic upgrade head`
4. Start the API:
   `poetry run uvicorn thingdex.main:app --reload`

The API listens on `http://127.0.0.1:8000` and exposes OpenAPI docs at `/docs`.

## Configuration
- `DATABASE_URL` (default: `postgresql+psycopg://thingdex:thingdex@localhost:5432/thingdex`)
- `ROOT_LOCATION_NAME` (default: `World`)
- `LABEL_PRINTING_ENABLED` (default: `false`)
- `LABEL_API_BASE` (default: `http://label.xn--jahnstrae-n1a.de/api/v1`)
- `PRINTHUB_API_BASE` (default: `http://printhub.xn--jahnstrae-n1a.de`)
- `LABEL_CONTAINER_TEMPLATE_ID` (default: `container-name`)

## API Documentation Export
- Generate a portable OpenAPI spec: `poetry run python scripts/export_openapi.py`
- See additional notes in `api-doc.md`
