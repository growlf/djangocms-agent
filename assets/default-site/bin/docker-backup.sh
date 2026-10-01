#!/usr/bin/env bash
# Back up the running Docker stack: the PostgreSQL database (db.sql) AND the media volume
# (media.tar.gz; uploads/filer files are NOT part of a pg_dump).
# Usage: bin/docker-backup.sh [BACKUP_DIR]       (default: backups/<UTC timestamp>)
# Another compose project name: COMPOSE_PROJECT_NAME=name bin/docker-backup.sh
# Refuses to write into an existing directory. The stack must be running (db and app up).
set -euo pipefail
cd "$(dirname "$0")/.."

dir="${1:-backups/$(date -u +%Y%m%dT%H%M%SZ)}"
if [ -e "$dir" ]; then echo "Refusing to overwrite existing $dir" >&2; exit 1; fi
mkdir -p "$dir"
trap 'rc=$?; [ $rc -eq 0 ] || { echo "Backup failed; removing partial $dir" >&2; rm -rf "$dir"; }' EXIT

echo "Dumping the database..."
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$dir/db.sql"
[ -s "$dir/db.sql" ] || { echo "Empty database dump" >&2; exit 1; }
echo "Archiving the media volume..."
docker compose exec -T app tar -C /app/media -czf - . > "$dir/media.tar.gz"
tar -tzf "$dir/media.tar.gz" >/dev/null
chmod 600 "$dir/db.sql" "$dir/media.tar.gz"
echo "Backup written to $dir (db.sql, media.tar.gz). Keep it private: it contains all site data."
