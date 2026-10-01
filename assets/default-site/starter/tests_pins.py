"""Tests for bin/pin_images.py (no network, no containers): digest pins on Dockerfile and compose images."""
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import SkipTest, skipUnless

from django.test import SimpleTestCase

BASE = Path(__file__).resolve().parent.parent
if not (BASE / "bin" / "pin_images.py").exists():
    raise SkipTest("site was created with --no-docker: no image pins to test")

D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64

spec = importlib.util.spec_from_file_location("pin_images", BASE / "bin" / "pin_images.py")
pin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pin)

DOCKERFILE = """# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
RUN true
FROM base AS dev
FROM --platform=linux/amd64 node:20-alpine@sha256:%s AS assets
FROM scratch
FROM ${BASE_IMAGE}
FROM base AS production
""" % ("9" * 64)

COMPOSE = """name: demo
services:
  db:
    image: postgres:16-alpine
  app:
    image: ${APP_IMAGE:-demo}:${APP_VERSION:-latest}
    build: .
  cache:
    image: "redis:7"  # quoted with a comment
"""

TABLE = {"python:3.12-slim": D1, "node:20-alpine": D2, "postgres:16-alpine": D3, "redis:7": D1}


def fake(name, tag):
    return TABLE[f"{name}:{tag}"]


class PinRewriteTests(SimpleTestCase):
    def test_dockerfile_pins_only_external_images(self):
        new, report = pin.rewrite(Path("Dockerfile"), DOCKERFILE, fake)
        lines = new.splitlines()
        self.assertEqual(lines[1], f"FROM python:3.12-slim@{D1} AS base")
        self.assertEqual(lines[3], "FROM base AS dev")                      # earlier stage: untouched
        self.assertEqual(lines[4], f"FROM --platform=linux/amd64 node:20-alpine@{D2} AS assets")  # old digest replaced
        self.assertEqual(lines[5], "FROM scratch")
        self.assertEqual(lines[6], "FROM ${BASE_IMAGE}")                    # variable: untouched
        self.assertEqual(lines[7], "FROM base AS production")
        self.assertEqual([(r[0], r[1]) for r in report], [("python:3.12-slim", "added"), ("node:20-alpine", "updated")])

    def test_compose_pins_and_keeps_quotes_comments_and_variable_images(self):
        new, report = pin.rewrite(Path("docker-compose.yml"), COMPOSE, fake)
        self.assertIn(f"    image: postgres:16-alpine@{D3}\n", new)
        self.assertIn("image: ${APP_IMAGE:-demo}:${APP_VERSION:-latest}\n", new)
        self.assertIn(f'    image: "redis:7@{D1}"  # quoted with a comment', new)
        self.assertEqual(len(report), 2)

    def test_idempotent(self):
        once, _ = pin.rewrite(Path("Dockerfile"), DOCKERFILE, fake)
        twice, report = pin.rewrite(Path("Dockerfile"), once, fake)
        self.assertEqual(once, twice)
        self.assertTrue(all(r[1] == "ok" for r in report))

    def test_reference_without_tag_is_an_error(self):
        with self.assertRaises(pin.PinError):
            pin.rewrite(Path("Dockerfile"), "FROM python\n", fake)

    def test_registry_and_repo_normalisation(self):
        self.assertEqual(pin._registry_and_repo("postgres"), ("registry-1.docker.io", "library/postgres"))
        self.assertEqual(pin._registry_and_repo("grafana/grafana"), ("registry-1.docker.io", "grafana/grafana"))
        self.assertEqual(pin._registry_and_repo("ghcr.io/org/img"), ("ghcr.io", "org/img"))
        self.assertEqual(pin._registry_and_repo("docker.io/library/python"), ("registry-1.docker.io", "library/python"))

    def test_fake_digest_table_is_used_without_network(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"python:3.12-slim": D1}, fh)
        try:
            os.environ["PIN_IMAGES_FAKE_DIGESTS"] = fh.name
            self.assertEqual(pin.resolve_digest("python", "3.12-slim"), D1)
            with self.assertRaises(pin.PinError):
                pin.resolve_digest("nope", "1")
        finally:
            os.environ.pop("PIN_IMAGES_FAKE_DIGESTS", None)
            os.unlink(fh.name)

    @skipUnless(os.environ.get("PIN_IMAGES_LIVE") == "1", "set PIN_IMAGES_LIVE=1 to query the real registry")
    def test_live_registry_returns_a_digest(self):
        self.assertRegex(pin.resolve_digest("python", "3.12-slim"), r"^sha256:[0-9a-f]{64}$")


class PinCommandTests(SimpleTestCase):
    def repo(self, dockerfile=DOCKERFILE, compose=COMPOSE, commit=True):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "Dockerfile").write_text(dockerfile)
        (tmp / "docker-compose.yml").write_text(compose)
        (tmp / "docker-compose.dev.yml").write_text("services:\n  db:\n    image: postgres:16-alpine\n")
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
        if commit:
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"], cwd=tmp, check=True)
        return tmp

    def run_main(self, tmp, *args):
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = pin.main(list(args), root=tmp, resolve=fake)
        return rc, out.getvalue(), err.getvalue()

    def test_check_fails_on_missing_then_passes_after_write(self):
        tmp = self.repo()
        rc, out, _ = self.run_main(tmp, "--check")
        self.assertEqual(rc, 1)
        self.assertIn("MISSING", out)
        rc, out, _ = self.run_main(tmp)                  # write mode on a clean tree
        self.assertEqual(rc, 0)
        self.assertIn(f"postgres:16-alpine@{D3}", (tmp / "docker-compose.dev.yml").read_text())
        self.assertEqual(self.run_main(tmp, "--check")[0], 0)

    def test_check_fails_on_a_stale_pin(self):
        tmp = self.repo()
        self.run_main(tmp, "--allow-dirty")
        text = (tmp / "docker-compose.yml").read_text().replace(D3, "sha256:" + "0" * 64)
        (tmp / "docker-compose.yml").write_text(text)
        rc, out, _ = self.run_main(tmp, "--check")
        self.assertEqual(rc, 1)
        self.assertIn("STALE", out)
        self.assertIn("was sha256:" + "0" * 8, out)

    def test_dry_run_writes_nothing(self):
        tmp = self.repo()
        before = (tmp / "Dockerfile").read_text()
        rc, out, _ = self.run_main(tmp, "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("WOULD ADD", out)
        self.assertEqual((tmp / "Dockerfile").read_text(), before)

    def test_write_mode_refuses_a_dirty_tree(self):
        tmp = self.repo()
        (tmp / "README.md").write_text("dirty\n")
        rc, _out, err = self.run_main(tmp)
        self.assertEqual(rc, 2)
        self.assertIn("dirty", err)
        self.assertNotIn("@sha256", (tmp / "Dockerfile").read_text().split("\n")[1])
        self.assertEqual(self.run_main(tmp, "--check")[0], 1)   # --check is read-only and works on a dirty tree

    def test_cli_wrapper_with_fake_digests(self):
        """bin/pin-images.sh --check against the real project files with a digest table built from them."""
        refs = {}
        for path in pin.tracked_files(BASE):
            for _i, ref in pin.find_references(path, path.read_text()):
                name, tag, digest = pin.split_ref(ref)
                refs[f"{name}:{tag}"] = digest
        self.assertTrue(refs and all(refs.values()), "every external image in the repo must carry a digest")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(refs, fh)
        try:
            env = {**os.environ, "PIN_IMAGES_FAKE_DIGESTS": fh.name}
            ok = subprocess.run([str(BASE / "bin" / "pin-images.sh"), "--check"], env=env, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            stale = {k: "sha256:" + "f" * 64 for k in refs}
            Path(fh.name).write_text(json.dumps(stale))
            bad = subprocess.run([str(BASE / "bin" / "pin-images.sh"), "--check"], env=env, capture_output=True, text=True)
            self.assertEqual(bad.returncode, 1)
            self.assertIn("STALE", bad.stdout)
        finally:
            os.unlink(fh.name)

    def test_project_images_are_pinned_with_their_tag_visible(self):
        for path in pin.tracked_files(BASE):
            for _i, ref in pin.find_references(path, path.read_text()):
                name, tag, digest = pin.split_ref(ref)
                self.assertTrue(tag, f"{path.name}: {ref} needs a tag")
                self.assertRegex(digest or "", r"^sha256:[0-9a-f]{64}$", f"{path.name}: {ref} is not pinned")
