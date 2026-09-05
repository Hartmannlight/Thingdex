# Configuration

Thingdex is configured exclusively through environment variables. It does not
load `.env` files directly. Use `.env.example` as a template for your shell,
service manager, secret store, or container runtime.

## Application variables

| Variable | Default | Required in production | Description |
| --- | --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://thingdex:thingdex@127.0.0.1:5432/thingdex` | Yes | SQLAlchemy/psycopg PostgreSQL URL used by the API and Alembic |
| `ROOT_LOCATION_NAME` | `World` | No | Name assigned only when the root location is first created |
| `LABEL_PRINTING_ENABLED` | `false` | No | Enables durable PrintHub intents; inventory requests never wait for PrintHub |
| `PRINTHUB_API_BASE` | `http://printhub:8000` | In the print worker | Base URL of the optional PrintHub job service |
| `PRINTHUB_API_TOKEN` | unset | Yes when PrintHub requires authentication | Worker-to-PrintHub bearer credential |
| `THINGDEX_PRINT_ADMIN_TOKEN` | unset | Yes for outbox administration | Bearer token for reading and retrying `/v1/print-intents` |
| `THINGDEX_PRINTHUB_EVENT_SECRET` | unset | Yes for status events | HMAC-SHA256 secret for the replay-safe PrintHub event inbox |
| `THINGDEX_PRINT_WORKER_INTERVAL_SECONDS` | `1` | No | Idle polling interval of the separately run print worker |
| `THINGDEX_PRINT_MAX_ATTEMPTS` | `10` | No | Attempts before an intent requires an explicit authenticated retry |
| `LABEL_API_BASE` | derived as `${PRINTHUB_API_BASE}/v1` | Legacy migration only | Optional override for an older separate template service |
| `LABEL_CONTAINER_TEMPLATE_ID` | `container-name` | No | Fallback template ID for location labels |

Boolean parsing for `LABEL_PRINTING_ENABLED` accepts `1`, `true`, `yes`, and
`on`, case-insensitively. Every other value disables printing.

## Test-only variables

| Variable | Default | Description |
| --- | --- | --- |
| `THINGDEX_TEST_DATABASE_URL` | Falls back to `DATABASE_URL` | Base PostgreSQL database used to create isolated schemas for tests |

Tests create and drop a unique schema per fixture. Never point the test variable
at a PostgreSQL role that should not have schema-management rights.

## URL details

The database URL must use the psycopg SQLAlchemy dialect:

```text
postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE
```

Percent-encode reserved characters in credentials. Inside a container, the
host must be a reachable PostgreSQL service name or address; `127.0.0.1` refers
to the API container itself.

## Secrets

Treat `DATABASE_URL`, `PRINTHUB_API_TOKEN`, `THINGDEX_PRINT_ADMIN_TOKEN` and
`THINGDEX_PRINTHUB_EVENT_SECRET` as
secrets. Inject them at runtime and avoid committing a
real value to `.env.example`, container images, OpenAPI documents, or logs.
The label URLs are configuration, but any credentials embedded in those URLs
must be handled with the same care.
