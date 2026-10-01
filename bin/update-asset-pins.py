#!/usr/bin/env python3
"""Keep the Docker image pins of the scaffold assets current (maintainer command for this skill repo).

The generated sites pin every image by digest (`name:tag@sha256:<index digest>`). The pins in
`assets/default-site/` (Dockerfile, docker-compose.yml, docker-compose.dev.yml) age: registries move
the tags. Run this before every skill release, and whenever a base image tag is bumped:

    bin/update-asset-pins.py --check     exit 1 when a pin is missing or stale (needs network, read-only)
    bin/update-asset-pins.py --dry-run   show what would change
    bin/update-asset-pins.py             rewrite the pins in assets/default-site (review `git diff`, commit)

It drives the same tool the generated sites ship (`assets/default-site/bin/pin_images.py`, registry HTTP
API only, no Docker daemon, no pull). `PIN_IMAGES_FAKE_DIGESTS=<json>` replaces the network for tests.
The offline guard `tests/test_asset_pins.py` checks that the pins are well formed; the live comparison is
this script's `--check` (or `ASSET_PINS_LIVE=1 python -m pytest tests/test_asset_pins.py`).
Exit codes follow pin_images.py: 0 ok, 1 stale/missing pin (--check), 2 usage or lookup error.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "assets" / "default-site"
TOOL = SITE / "bin" / "pin_images.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("pin_images", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not TOOL.exists():
        print(f"error: {TOOL} is missing", file=sys.stderr)
        return 2
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0
    write = not any(a in ("--check", "--dry-run") for a in argv)
    if write and "--allow-dirty" not in argv:
        argv.append("--allow-dirty")  # this is a maintainer edit of a repo checkout; the diff is the review
    return load_tool().main(argv, root=SITE)


if __name__ == "__main__":
    sys.exit(main())
