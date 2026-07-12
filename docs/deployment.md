# Deployment

Multi-service orchestration belongs to the
[Thingdex Home Inventory](https://github.com/Hartmannlight/Thingdex-Home-Inventory)
repository. This repository publishes the independently runnable backend image
and defines its operational contract.

## Build the image

```shell
docker build -t thingdex:local .
```

The image:

- installs only runtime dependencies;
- runs as the unprivileged `thingdex` user;
- applies `alembic upgrade head` in its entrypoint;
- starts Uvicorn on port `8000`;
- includes a readiness-based Docker health check.

## Runtime contract

The orchestrator must provide:

1. a reachable PostgreSQL 15+ database;
2. all required [environment variables](configuration.md);
3. persistent PostgreSQL storage and a tested backup policy;
4. network access to optional label services when enabled;
5. routing only after `/health/ready` succeeds.

Example for a PostgreSQL service reachable as `postgres`:

```shell
docker run --rm \
  --name thingdex-api \
  --network thingdex \
  --env DATABASE_URL=postgresql+psycopg://thingdex:password@postgres:5432/thingdex \
  --publish 8000:8000 \
  thingdex:local
```

Do not add `--reload` in production.

## Migrations

The container entrypoint upgrades the database before Uvicorn starts. Run one
migrating instance at a time during deployment; do not race several new
containers against the same unupgraded database.

Before deployment, CI should run:

```shell
poetry run alembic upgrade head
poetry run alembic check
```

Migration `0007_inventory_invariants` repairs parentless non-root locations by
attaching them to the canonical root before enabling stricter constraints. A
database with conflicting relation data fails migration instead of silently
discarding inventory information.

## Health checks

| Endpoint | Use |
| --- | --- |
| `/health/live` | Restart a wedged API process |
| `/health/ready` | Decide whether to route traffic |
| `/health` | Compatibility alias for readiness |

Readiness returns `503` when PostgreSQL is unavailable or the inventory root is
missing.

## Backup and recovery

Backups are an orchestration concern because PostgreSQL owns the durable data.
At minimum:

- create scheduled `pg_dump --format=custom` backups;
- retain copies on storage independent of the database host;
- protect backup credentials and files;
- rehearse `pg_restore --clean --if-exists --exit-on-error` into a separate
  database;
- verify both `alembic_version` and representative inventory records.

The backend repository intentionally contains no Docker Compose file. This
prevents local development orchestration from becoming an accidental
production definition and keeps the system topology centralized in the main
repository.
