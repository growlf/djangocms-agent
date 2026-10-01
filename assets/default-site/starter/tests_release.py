"""Tests for bin/release.sh, the prod/dev Docker file split and the backup/restore/dev helper scripts
(no network, no containers: docker is replaced by a recording stub where a script would call it)."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import skipUnless

from django.test import SimpleTestCase

BASE = Path(__file__).resolve().parent.parent
docker_only = unittest.skipUnless((BASE / "Dockerfile").exists(), "site was created with --no-docker: no container files to check")

CHANGELOG = """# Changelog

## [Unreleased]

### Added
- Something new.
"""


class ReleaseScriptTests(SimpleTestCase):
    def repo(self, branch="main"):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "bin").mkdir()
        shutil.copy(BASE / "bin" / "release.sh", tmp / "bin" / "release.sh")
        (tmp / "Dockerfile").write_text("FROM python:3.12-slim\n")
        (tmp / "CHANGELOG.md").write_text(CHANGELOG)
        git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *a], cwd=tmp, check=True, capture_output=True, text=True)  # noqa: E731
        git("init", "-q", "-b", branch)
        git("add", "-A")
        git("commit", "-qm", "init")
        self.git = git
        return tmp

    def release(self, tmp, *args, pin_cmd="true", test_cmd="true"):
        env = {**os.environ, "RELEASE_PIN_CMD": pin_cmd, "RELEASE_TEST_CMD": test_cmd,
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com"}
        return subprocess.run(["bash", "bin/release.sh", *args], cwd=tmp, env=env, capture_output=True, text=True)

    def test_rejects_bad_versions(self):
        tmp = self.repo()
        for bad in ("1.2.3", "v1.2", "v1.2.x", "latest", "v01.2.3"):
            r = self.release(tmp, bad)
            self.assertEqual(r.returncode, 2, bad)
        self.assertEqual(self.release(tmp).returncode, 2)  # no version

    def test_refuses_dirty_tree_and_wrong_branch(self):
        tmp = self.repo()
        (tmp / "x").write_text("dirty")
        r = self.release(tmp, "v1.0.0")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not clean", r.stderr)
        tmp = self.repo(branch="feature")
        r = self.release(tmp, "v1.0.0")
        self.assertEqual(r.returncode, 1)
        self.assertIn("main", r.stderr)
        self.assertEqual(self.release(tmp, "v1.0.0", "--force-branch").returncode, 0)

    def test_version_must_be_newer_than_the_latest_tag(self):
        tmp = self.repo()
        self.git("tag", "-a", "v1.4.0", "-m", "x")
        for old in ("v1.3.9", "v1.4.0", "v0.9.0"):
            r = self.release(tmp, old)
            self.assertEqual(r.returncode, 1, old)
        self.assertEqual(self.release(tmp, "v1.10.0").returncode, 0)   # 1.10.0 > 1.4.0 (numeric, not text, order)

    def test_dry_run_changes_nothing(self):
        tmp = self.repo()
        head = self.git("rev-parse", "HEAD").stdout
        r = self.release(tmp, "v1.0.0", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[dry-run] would", r.stdout)
        self.assertEqual(self.git("rev-parse", "HEAD").stdout, head)
        self.assertEqual(self.git("tag").stdout, "")
        self.assertFalse((tmp / "VERSION").exists())
        self.assertEqual(self.git("status", "--porcelain").stdout, "")

    def test_real_release_commits_tags_and_prints_push_commands(self):
        tmp = self.repo()
        pin_cmd = "echo 'FROM python:3.12-slim@sha256:%s' > Dockerfile" % ("a" * 64)  # stub: pins refreshed
        r = self.release(tmp, "v1.2.3", pin_cmd=pin_cmd)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((tmp / "VERSION").read_text(), "1.2.3\n")
        changelog = (tmp / "CHANGELOG.md").read_text()
        self.assertRegex(changelog, r"## \[Unreleased\]\n\n## \[1\.2\.3\] - \d{4}-\d\d-\d\d\n\n### Added")
        self.assertEqual(changelog.count("## [1.2.3]"), 1)
        self.assertEqual(self.git("log", "-1", "--format=%s").stdout.strip(), "Release v1.2.3")
        files = self.git("show", "--name-only", "--format=", "HEAD").stdout.split()
        self.assertEqual(sorted(files), ["CHANGELOG.md", "Dockerfile", "VERSION"])   # the refreshed pin is part of the release
        self.assertEqual(self.git("cat-file", "-t", "v1.2.3").stdout.strip(), "tag")  # annotated
        self.assertIn("git push origin v1.2.3", r.stdout)
        self.assertIn("git push origin main", r.stdout)
        self.assertEqual(self.git("status", "--porcelain").stdout, "")
        again = self.release(tmp, "v1.2.3")
        self.assertEqual(again.returncode, 1)
        self.assertIn("already exists", again.stderr)

    def test_failing_tests_leave_no_commit_or_tag(self):
        tmp = self.repo()
        head = self.git("rev-parse", "HEAD").stdout
        r = self.release(tmp, "v1.0.0", test_cmd="false")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.git("rev-parse", "HEAD").stdout, head)
        self.assertEqual(self.git("tag").stdout, "")
        self.assertFalse((tmp / "VERSION").exists())

    def test_it_never_pushes(self):
        self.assertNotRegex((BASE / "bin" / "release.sh").read_text().replace("git push origin", ""), r"git push")


@docker_only
class ComposeSplitTests(SimpleTestCase):
    def setUp(self):
        self.prod = (BASE / "docker-compose.yml").read_text()
        self.dev = (BASE / "docker-compose.dev.yml").read_text()

    def test_production_file_has_no_dev_settings(self):
        self.assertNotRegex(self.prod, r'DJANGO_DEBUG:\s*"1"')
        self.assertNotIn("DJANGO_DEBUG_TOOLBAR_ANY_IP", self.prod)
        self.assertNotIn("- .:/app", self.prod)
        self.assertNotIn("runserver", self.prod)
        self.assertIn("target: production", self.prod)

    def test_dev_file_is_separate_loopback_only_and_dev_flavoured(self):
        self.assertIn("name: __PROJECT_NAME__-dev", self.dev)
        self.assertIn('DJANGO_DEBUG: "1"', self.dev)
        self.assertIn("target: dev", self.dev)
        self.assertIn(".:/app", self.dev)
        self.assertIn("healthcheck:", self.dev)
        for port in re.findall(r'^\s*-\s*"([^"]*:\d+:\d+)"', self.dev, re.M):
            self.assertTrue(port.startswith("127.0.0.1:"), port)
        self.assertNotIn("8889", self.dev)                   # not the production port
        self.assertIn("${DEV_PORT:-8880}", self.dev)
        for volume in re.findall(r"^  (\w+):\s*$", self.dev.split("\nvolumes:\n", 1)[1], re.M):
            self.assertIn("dev", volume)                      # volume names never collide with the production ones

    def test_dev_image_and_project_names_differ_from_production(self):
        self.assertNotIn("name: __PROJECT_NAME__\n", self.dev)
        self.assertIn("__PROJECT_NAME__-dev", self.dev)

    def test_app_image_tag_convention(self):
        self.assertIn("image: ${APP_IMAGE:-__PROJECT_NAME__}:${APP_VERSION:-latest}", self.prod)

    def test_dockerfile_default_target_is_production_and_dev_installs_dev_requirements(self):
        text = (BASE / "Dockerfile").read_text()
        stages = re.findall(r"^FROM .* AS (\w+)$", text, re.M)
        self.assertEqual(stages[-1], "production")           # the last stage is what a plain `docker build` produces
        dev_block = text[text.index("AS dev"):text.index("AS production")]
        self.assertIn("requirements-dev.txt", dev_block)
        prod_block = text[text.index("AS production"):]
        self.assertNotIn("requirements-dev", prod_block)

    @skipUnless(shutil.which("docker"), "docker not installed")
    def test_both_compose_files_parse(self):
        env = {**os.environ, "DB_PASSWORD": "x", "DJANGO_SECRET_KEY": "x"}
        for name in ("docker-compose.yml", "docker-compose.dev.yml"):
            r = subprocess.run(["docker", "compose", "-f", name, "config", "-q"], cwd=BASE, env=env, capture_output=True, text=True)
            if r.returncode != 0 and "unknown shorthand flag" in r.stderr + r.stdout:
                self.skipTest("docker compose plugin not available")
            self.assertEqual(r.returncode, 0, r.stderr)


@docker_only
class HelperScriptTests(SimpleTestCase):
    """bin/docker-backup.sh, docker-restore.sh and the down scripts, run against a recording `docker` stub."""

    def stub_env(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        bin_dir = tmp / "stubbin"
        bin_dir.mkdir()
        log = tmp / "docker.log"
        stub = bin_dir / "docker"
        stub.write_text('#!/bin/sh\necho "$@" >> "%s"\ncase "$*" in *"count(*)"*) echo "${STUB_TABLES:-0}";; esac\nexit 0\n' % log)
        stub.chmod(0o755)
        return tmp, log, {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}

    def site_copy(self, tmp):
        site = tmp / "site"
        (site / "bin").mkdir(parents=True)
        for name in ("docker-backup.sh", "docker-restore.sh", "docker-down.sh", "dev-down.sh"):
            shutil.copy(BASE / "bin" / name, site / "bin" / name)
        (site / "docker-compose.dev.yml").write_text("services: {}\n")
        return site

    def run_script(self, site, env, name, *args):
        return subprocess.run(["bash", f"bin/{name}", *args], cwd=site, env=env, capture_output=True, text=True)

    def test_backup_refuses_an_existing_directory_and_touches_nothing(self):
        tmp, log, env = self.stub_env()
        site = self.site_copy(tmp)
        (site / "old").mkdir()
        (site / "old" / "keep").write_text("x")
        r = self.run_script(site, env, "docker-backup.sh", "old")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Refusing to overwrite", r.stderr)
        self.assertEqual((site / "old" / "keep").read_text(), "x")
        self.assertFalse(log.exists())  # docker was never called

    def test_backup_removes_a_partial_directory_on_failure(self):
        tmp, log, env = self.stub_env()
        site = self.site_copy(tmp)
        r = self.run_script(site, env, "docker-backup.sh", "new")   # the stub dumps nothing: empty db.sql
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((site / "new").exists())

    def test_restore_needs_a_dump_and_never_wipes_by_default(self):
        tmp, log, env = self.stub_env()
        site = self.site_copy(tmp)
        self.assertEqual(self.run_script(site, env, "docker-restore.sh").returncode, 2)
        self.assertEqual(self.run_script(site, env, "docker-restore.sh", "nope").returncode, 1)
        (site / "bk").mkdir()
        (site / "bk" / "db.sql").write_text("select 1;\n")
        r = self.run_script(site, {**env, "STUB_TABLES": "42"}, "docker-restore.sh", "bk")
        self.assertEqual(r.returncode, 1)
        self.assertIn("refusing to restore", r.stderr)
        calls = log.read_text()
        self.assertNotIn("down", calls)          # no `down -v` without --wipe
        self.assertNotIn("psql -v ON_ERROR_STOP", calls)

    def test_restore_loads_into_an_empty_database_with_on_error_stop_and_starts_app_last(self):
        tmp, log, env = self.stub_env()
        site = self.site_copy(tmp)
        (site / "bk").mkdir()
        (site / "bk" / "db.sql").write_text("select 1;\n")
        r = self.run_script(site, env, "docker-restore.sh", "bk")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = log.read_text().splitlines()
        load = next(i for i, c in enumerate(calls) if "ON_ERROR_STOP=1" in c)
        up_db = next(i for i, c in enumerate(calls) if c.endswith("up -d --wait db"))
        up_app = next(i for i, c in enumerate(calls) if c.endswith("up -d --wait app"))
        self.assertLess(up_db, load)
        self.assertLess(load, up_app)

    def test_restore_wipe_runs_down_v_only_when_asked(self):
        tmp, log, env = self.stub_env()
        site = self.site_copy(tmp)
        (site / "bk").mkdir()
        (site / "bk" / "db.sql").write_text("select 1;\n")
        self.run_script(site, env, "docker-restore.sh", "bk", "--wipe")
        self.assertIn("compose down -v", log.read_text())

    def test_down_scripts_keep_volumes_unless_asked(self):
        for script, extra in (("docker-down.sh", []), ("dev-down.sh", ["-f", "docker-compose.dev.yml"])):
            tmp, log, env = self.stub_env()
            site = self.site_copy(tmp)
            self.assertEqual(self.run_script(site, env, script).returncode, 0)
            self.assertNotRegex(log.read_text(), r"\bdown\b.*\s-v\b", script)
            r = self.run_script(site, env, script, "--volumes")
            self.assertIn("WARNING", r.stderr)
            self.assertRegex(log.read_text().splitlines()[-1], r"down -v$", script)
