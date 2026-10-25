#!/bin/sh
# backend/docker-entrypoint.sh
#
# 1. applies database migrations (aborts the container on failure),
# 2. starts gunicorn on 0.0.0.0:${PORT:-5000} unless another command is given.
#
# Environment:
#   PORT               listen port (default 5000; Railway injects it)
#   WEB_CONCURRENCY    gunicorn worker processes (default 2)
#   GUNICORN_THREADS   threads per worker (default 4)
#   GUNICORN_TIMEOUT   worker timeout in seconds (default 60)
#   RUN_MIGRATIONS     set to 0 to skip `flask db upgrade` (default 1)

set -eu

export FLASK_APP='app:create_app()'
PYTHON=/app/.venv/bin/python

if [ "${RUN_MIGRATIONS:-1}" != "0" ]; then
  echo "Running database migrations..."
  # create_app() also validates SECRET_KEY / JWT_SECRET_KEY, so a bad configuration
  # fails here, before anything is served.
  if ! "$PYTHON" -m flask db upgrade; then
    echo "ERROR: database migration failed (bad DATABASE_URL, database unreachable," >&2
    echo "       insecure/missing SECRET_KEY or JWT_SECRET_KEY, or a broken migration)." >&2
    echo "       Refusing to start. See the error above." >&2
    exit 1
  fi
  echo "Migrations complete."
else
  echo "RUN_MIGRATIONS=0: skipping migrations."
fi

if [ "$#" -eq 0 ]; then
  set -- "$PYTHON" -m gunicorn \
    --bind "0.0.0.0:${PORT:-5000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --worker-class gthread \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-60}" \
    --access-logfile - \
    --error-logfile - \
    'app:create_app()'
fi

echo "Executing: $*"
exec "$@"
