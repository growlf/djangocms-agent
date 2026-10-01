#!/usr/bin/env bash
# Stop the Docker stack. Data volumes are KEPT unless --volumes is given explicitly.
# Other args are passed to `docker compose` (e.g. -p other-name).
set -euo pipefail
cd "$(dirname "$0")/.."

vol=()
args=()
for a in "$@"; do
    if [ "$a" = "--volumes" ]; then vol=(-v); else args+=("$a"); fi
done
if [ "${#vol[@]}" -gt 0 ]; then
    echo "WARNING: removing this project's named volumes (database, media, static)." >&2
fi
docker compose ${args[@]+"${args[@]}"} down ${vol[@]+"${vol[@]}"}
