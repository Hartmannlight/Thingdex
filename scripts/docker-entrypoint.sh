#!/bin/sh
set -eu

if [ "${THINGDEX_RUN_MIGRATIONS:-true}" = "true" ]; then
    python -m alembic upgrade head
fi
exec "$@"
