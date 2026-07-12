# Configuration

Thingdex is configured exclusively through environment variables. It does not
load `.env` files directly. Use `.env.example` as a template for your shell,
service manager, secret store, or container runtime.

## Application variables

| Variable | Default | Required in production | Description |
| --- | --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://thingdex:thingdex@127.0.0.1:5432/thingdex` | Yes | SQLAlchemy/psycopg PostgreSQL URL used by the API and Alembic |
| `ROOT_LOCATION_NAME` | `World` | No | Name assigned only when the root location is first created |
| `LABEL_PRINTING_ENABLED` | `false` | No | Enables template lookup and synchronous print operations |
| `PRINTHUB_API_BASE` | `http://printhub.xn--jahnstrae-n1a.de` | When labels are enabled | Base URL of the optional PrintHub template and job service |
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

Treat `DATABASE_URL` as a secret. Inject it at runtime and avoid committing a
real value to `.env.example`, container images, OpenAPI documents, or logs.
The label URLs are configuration, but any credentials embedded in those URLs
must be handled with the same care.
