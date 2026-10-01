#!/usr/bin/env bash
# Dev container boot (docker-compose.dev.yml): wait for PostgreSQL, migrate, create the cache table,
# seed a fresh database once, then runserver with autoreload on the bind-mounted source.
set -euo pipefail

echo "Waiting for PostgreSQL at ${DB_HOST:-db}:${DB_PORT:-5432}..."
python - <<'PY'
import os, socket, sys, time
deadline = time.time() + 60
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

python manage.py migrate --noinput
python manage.py createcachetable
if [ "${SEED_ON_START:-1}" = "1" ]; then
    python manage.py seed --first-run-only
fi
echo "Starting runserver (autoreload on)..."
exec python manage.py runserver 0.0.0.0:8000
