#!/bin/sh
set -eu

if [ "${THINGDEX_RUN_MIGRATIONS:-true}" = "true" ]; then
    alembic upgrade head
fi
exec "$@"
