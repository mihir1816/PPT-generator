#!/bin/sh
set -e

if [ "${SKIP_MIGRATIONS:-false}" != "true" ]; then
  echo "Running database migrations..."
  alembic upgrade head
else
  echo "Skipping migrations (SKIP_MIGRATIONS=true)"
fi

echo "Starting application server..."
exec "$@"
