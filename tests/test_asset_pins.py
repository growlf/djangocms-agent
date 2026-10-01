"""The Docker image pins in assets/default-site must be well formed and refreshable (offline).

Whether they are CURRENT needs the network: `bin/update-asset-pins.py --check` (or ASSET_PINS_LIVE=1 here).
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "assets" / "default-site"
SCRIPT = REPO / "bin" / "update-asset-pins.py"

spec = importlib.util.spec_from_file_location("pin_images", SITE / "bin" / "pin_images.py")
pin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pin)


def refs():
    out = []
    for path in pin.tracked_files(SITE):
        for _i, ref in pin.find_references(path, path.read_text()):
            out.append((path.name, ref))
    return out


def test_every_external_image_is_pinned_by_index_digest_with_a_visible_tag():
    found = refs()
    assert {n for n, _ in found} >= {"Dockerfile", "docker-compose.yml", "docker-compose.dev.yml"}
    for fname, ref in found:
        name, tag, digest = pin.split_ref(ref)
        assert tag, f"{fname}: {ref} needs a readable tag"
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest or ""), f"{fname}: {ref} is not pinned by digest"
        assert digest != "sha256:" + "0" * 64


def test_the_same_image_has_the_same_digest_everywhere():
    seen = {}
    for fname, ref in refs():
        name, tag, digest = pin.split_ref(ref)
        assert seen.setdefault(f"{name}:{tag}", digest) == digest, f"{name}:{tag} pinned differently in {fname}"


def test_maintenance_script_check_ok_and_stale_with_fake_registry(tmp_path):
    table = {f"{pin.split_ref(r)[0]}:{pin.split_ref(r)[1]}": pin.split_ref(r)[2] for _, r in refs()}
    fake = tmp_path / "digests.json"
    fake.write_text(json.dumps(table))
    env = {**os.environ, "PIN_IMAGES_FAKE_DIGESTS": str(fake)}
    ok = subprocess.run([sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True, env=env)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "pins are current" in ok.stdout
    fake.write_text(json.dumps({k: "sha256:" + "f" * 64 for k in table}))
    stale = subprocess.run([sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True, env=env)
    assert stale.returncode == 1 and "STALE" in stale.stdout


def test_maintenance_script_dry_run_writes_nothing(tmp_path):
    before = {p: p.read_text() for p in pin.tracked_files(SITE)}
    table = {f"{pin.split_ref(r)[0]}:{pin.split_ref(r)[1]}": "sha256:" + "a" * 64 for _, r in refs()}
    fake = tmp_path / "digests.json"
    fake.write_text(json.dumps(table))
    env = {**os.environ, "PIN_IMAGES_FAKE_DIGESTS": str(fake)}
    r = subprocess.run([sys.executable, str(SCRIPT), "--dry-run"], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "WOULD UPDATE" in r.stdout
    assert {p: p.read_text() for p in pin.tracked_files(SITE)} == before


@pytest.mark.skipif(os.environ.get("ASSET_PINS_LIVE") != "1", reason="set ASSET_PINS_LIVE=1 to compare with the real registry")
def test_live_pins_are_current():
    r = subprocess.run([sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
