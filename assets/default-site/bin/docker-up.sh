#!/usr/bin/env bash
# Build and start the Docker stack, wait until the app is healthy, print the URL.
# Extra args are passed to `docker compose` before `up` (e.g. -p other-name).
# Host port: APP_PORT (environment or .env), default 8889. Set DJANGO_CSRF_TRUSTED_ORIGINS if you browse
# through another host name or a proxy.
set -euo pipefail
cd "$(dirname "$0")/.."

bin/docker-env.sh
docker compose "$@" up -d --build

cid=$(docker compose "$@" ps -q app)
echo "Waiting for the app to become healthy (up to 180s)..."
status=starting
for _ in $(seq 1 90); do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo starting)
    [ "$status" = "healthy" ] && break
    [ "$status" = "unhealthy" ] && { docker compose "$@" logs --tail 40 app; echo "App is unhealthy." >&2; exit 1; }
    sleep 2
done
[ "$status" = "healthy" ] || { echo "Timed out waiting for healthy app." >&2; exit 1; }

port="${APP_PORT:-$(set -a; [ -f .env ] && . ./.env; echo "${APP_PORT:-8889}")}"
echo "Ready: http://localhost:${port}/  (admin: http://localhost:${port}/admin/)"
echo "No admin user yet? docker compose $* exec app python manage.py createsuperuser"
