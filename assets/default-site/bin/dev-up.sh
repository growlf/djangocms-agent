#!/usr/bin/env bash
# Build and start the DEV stack (docker-compose.dev.yml: DEBUG, debug toolbar, source bind-mounted,
# autoreload) and wait until the app is healthy. Project name __PROJECT_NAME__-dev, default port 8880.
# Extra args are passed to `docker compose` before `up` (e.g. -p other-name).
set -euo pipefail
cd "$(dirname "$0")/.."

dc() { docker compose -f docker-compose.dev.yml "$@"; }
dc "$@" up -d --build

cid=$(dc "$@" ps -q app)
echo "Waiting for the dev app to become healthy (up to 240s)..."
for _ in $(seq 1 120); do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo starting)
    [ "$status" = "healthy" ] && break
    [ "$status" = "unhealthy" ] && { dc "$@" logs --tail 40 app; echo "Dev app is unhealthy." >&2; exit 1; }
    sleep 2
done
[ "${status:-}" = "healthy" ] || { echo "Timed out waiting for the dev app." >&2; exit 1; }
echo "Ready: http://localhost:${DEV_PORT:-8880}/  (admin: /admin/; create a user: docker compose -f docker-compose.dev.yml exec app python manage.py createsuperuser)"
