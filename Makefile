# Maintainer shortcuts for the skill repo (the skill itself needs no build step).
.PHONY: test pins pins-check

test:
	python3 -m pytest -q tests

# Rewrite the Docker image digest pins in assets/default-site (network: registry HTTP API). Review git diff.
pins:
	python3 bin/update-asset-pins.py

# Read-only: exit 1 when a pin in assets/default-site is missing or stale (network).
pins-check:
	python3 bin/update-asset-pins.py --check
