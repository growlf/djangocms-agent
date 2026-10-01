#!/usr/bin/env bash
# Pin the Docker base/compose images by digest (name:tag@sha256:...) and keep the pins current.
#   bin/pin-images.sh             rewrite pins in place (clean git tree required)
#   bin/pin-images.sh --dry-run   show changes only
#   bin/pin-images.sh --check     exit 1 when a pin is missing or stale
# Pins are refreshed with every vX.Y.Z release (bin/release.sh runs this). See bin/pin_images.py.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 bin/pin_images.py "$@"
