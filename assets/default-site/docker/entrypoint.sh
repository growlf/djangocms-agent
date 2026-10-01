#!/usr/bin/env bash
# Container boot: wait for DB, migrate, collectstatic, optional seed, then gunicorn.
set -euo pipefail

if [ "${DB_ENGINE:-}" = "postgres" ]; then
    timeout_s="${DB_WAIT_TIMEOUT:-60}"
    echo "Waiting for PostgreSQL at ${DB_HOST:-db}:${DB_PORT:-5432} (up to ${timeout_s}s)..."
    python - "$timeout_s" <<'PY'
import socket, sys, time, os
deadline = time.time() + float(sys.argv[1])
host, port = os.environ.get("DB_HOST", "db"), int(os.environ.get("DB_PORT", "5432"))
while True:
    try:
        socket.create_connection((host, port), timeout=2).close()
        break
    except OSError:
        if time.time() > deadline:
            sys.exit("PostgreSQL did not become reachable in time")
        time.sleep(1)
PY
fi

# WhiteNoise warns "No directory at: staticfiles/" if STATIC_ROOT is missing when Django starts.
mkdir -p staticfiles

echo "Applying migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput --verbosity 0

if [ "${CREATE_VERSIONS:-0}" = "1" ]; then
    echo "Creating versions for pre-versioning content..."
    python manage.py create_versions --state published --username "${CREATE_VERSIONS_USER:?set CREATE_VERSIONS_USER}"
fi

if [ "${SEED_ON_START:-0}" = "1" ]; then
    echo "Seeding (idempotent)..."
    python manage.py seed
fi

echo "Starting gunicorn..."
# --no-control-socket: the control socket needs a writable home; the non-root user has none.
exec gunicorn __PROJECT_NAME__.wsgi:application \
    --bind "0.0.0.0:8000" \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --graceful-timeout 30 \
    --no-control-socket \
    --access-logfile -
