#!/usr/bin/env bash
# Restore a backup made by bin/docker-backup.sh into the Docker stack.
# Usage: bin/docker-restore.sh BACKUP_DIR [--wipe]
# Another compose project name: COMPOSE_PROJECT_NAME=name bin/docker-restore.sh DIR
#
# Safe default: the database must be EMPTY (a fresh stack where only `db` has been started). If it
# is not, the script refuses and changes nothing. With --wipe it first runs `docker compose down -v`
# for THIS compose project (deleting its database, media and static volumes), which you must ask for.
# The order matters: restoring into a database the app has already migrated fails with hundreds of
# "already exists" errors, so the app is only started AFTER the dump is loaded.
set -euo pipefail
cd "$(dirname "$0")/.."

dir="${1:-}"; wipe=0
[ -n "$dir" ] || { sed -n '2,10p' "$0" >&2; exit 2; }
[ "${2:-}" = "--wipe" ] && wipe=1
[ -s "$dir/db.sql" ] || { echo "$dir/db.sql not found or empty" >&2; exit 1; }

if [ "$wipe" = 1 ]; then
    echo "WARNING: --wipe: deleting this compose project's volumes (database, media, static)." >&2
    docker compose down -v
fi

echo "Starting only the database..."
docker compose up -d --wait db
tables=$(docker compose exec -T db sh -c \
    "psql -U \"\$POSTGRES_USER\" \"\$POSTGRES_DB\" -Atc \"select count(*) from information_schema.tables where table_schema='public'\"")
if [ "$tables" != "0" ]; then
    echo "The database already has $tables tables; refusing to restore over it." >&2
    echo "Re-run with --wipe to delete this project's volumes first (data loss), or restore elsewhere." >&2
    exit 1
fi

echo "Restoring the database (stops at the first error)..."
docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" "$POSTGRES_DB"' < "$dir/db.sql" >/dev/null

echo "Starting the app..."
docker compose up -d --wait app
if [ -s "$dir/media.tar.gz" ]; then
    echo "Restoring media..."
    docker compose exec -T app tar -C /app/media -xzf - < "$dir/media.tar.gz"
else
    echo "No media.tar.gz in $dir: media files were not restored." >&2
fi
echo "Restore complete."
