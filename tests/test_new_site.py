"""Offline tests for bin/new-site.py (no network, no venv, no database)."""
import importlib.util
import os
import py_compile
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "new-site.py"

spec = importlib.util.spec_from_file_location("new_site", SCRIPT)
ns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ns)

PLACEHOLDERS = ("__PROJECT_NAME__", "__SITE_NAME__")


def cli(*args, cwd=None, stdin=subprocess.DEVNULL):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          cwd=cwd, stdin=stdin, env=env, timeout=120)


def scaffold(tmp_path, *extra, name="Acme Garden Club", purpose="Events for a garden club"):
    proc = cli("--name", name, "--purpose", purpose, "--parent-dir", str(tmp_path),
               "--no-venv", "--yes", *extra)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return tmp_path / ns.derive_names(name)[0]


def tree(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


# ---- names ---------------------------------------------------------------------------------

@pytest.mark.parametrize("name,slug,package", [
    ("Acme Garden Club", "acme-garden-club", "acme_garden_club"),
    ("my_site", "my-site", "my_site"),
    ("Café Münster", "cafe-munster", "cafe_munster"),
    ("A  B--C", "a-b-c", "a_b_c"),
])
def test_valid_names(name, slug, package):
    assert ns.derive_names(name) == (slug, package)
    assert package.isidentifier()


@pytest.mark.parametrize("bad", [
    "", "   ", "../evil", "a/b", "a\\b", ".hidden", "a..b", "123site", "!!!", "class", "django", "Test",
    "starter", "djangocms-foo", "x" * 65, "bad\x00name", "bad\nname",
])
def test_invalid_names(bad):
    with pytest.raises(ns.UsageError):
        ns.derive_names(bad)


def test_site_name_with_quotes_is_a_valid_python_string(tmp_path):
    root = scaffold(tmp_path, "--site-name", "Bob's \\ \"Best\" Site")
    settings = (root / "acme_garden_club" / "settings.py").read_text()
    ns_ = {}
    compile(settings, "settings.py", "exec")
    line = next(l for l in settings.splitlines() if l.startswith("SITE_NAME ="))
    exec(line.split("#")[0], ns_)
    assert ns_["SITE_NAME"] == "Bob's \\ \"Best\" Site"


# ---- CLI behaviour ---------------------------------------------------------------------------

def test_missing_args_non_interactive_exits_2(tmp_path):
    proc = cli(cwd=tmp_path)
    assert proc.returncode == 2
    assert "Ask the human" in proc.stderr
    assert list(tmp_path.iterdir()) == []
    proc = cli("--name", "Only Name", cwd=tmp_path)
    assert proc.returncode == 2 and "--purpose" in proc.stderr


def test_dry_run_touches_nothing(tmp_path):
    proc = cli("--name", "Acme", "--purpose", "x", "--parent-dir", str(tmp_path), "--dry-run")
    assert proc.returncode == 0, proc.stderr
    assert "Dry run" in proc.stdout and "write LICENSE" in proc.stdout
    assert list(tmp_path.iterdir()) == []


def test_refuses_existing_non_empty_dir(tmp_path):
    target = tmp_path / "acme"
    target.mkdir()
    (target / "keep.txt").write_text("precious")
    proc = cli("--name", "Acme", "--purpose", "x", "--parent-dir", str(tmp_path), "--no-venv", "--yes")
    assert proc.returncode == 2 and "refusing" in proc.stderr
    assert (target / "keep.txt").read_text() == "precious" and tree(target) == ["keep.txt"]


def test_accepts_existing_empty_dir(tmp_path):
    (tmp_path / "acme").mkdir()
    assert (scaffold(tmp_path, name="Acme") / "manage.py").is_file()


def test_unsupported_license_and_bad_parent(tmp_path):
    assert cli("--name", "Acme", "--purpose", "x", "--parent-dir", str(tmp_path), "--license", "GPL-9").returncode == 2
    assert cli("--name", "Acme", "--purpose", "x", "--parent-dir", str(tmp_path / "nope")).returncode == 2


def test_never_overwrites(tmp_path):
    root = scaffold(tmp_path, name="Acme")
    plan = ns.build_plan(ns.make_context(ns.build_parser().parse_args(
        ["--name", "Acme", "--purpose", "x", "--no-venv"])))
    with pytest.raises(ns.StepError, match="already exists"):
        ns.write_plan(plan, root)


# ---- generated project -----------------------------------------------------------------------

def test_scaffold_has_no_placeholders_in_contents_or_paths(tmp_path):
    root = scaffold(tmp_path)
    for rel in tree(root):
        if rel.startswith(".git/"):
            continue
        assert not any(p in rel for p in PLACEHOLDERS), rel
        data = (root / rel).read_bytes()
        for p in PLACEHOLDERS:
            assert p.encode() not in data, f"{p} left in {rel}"
        try:
            text = data.decode()
        except UnicodeDecodeError:
            continue
        assert not re.search(r"\{\{[A-Z_]+\}\}", text), f"unrendered FOSS token in {rel}"
    assert (root / "acme_garden_club" / "settings.py").is_file()
    assert not (root / "__PROJECT_NAME__").exists()


def test_python_files_compile_and_settings_point_at_package(tmp_path):
    root = scaffold(tmp_path)
    pys = [p for p in root.rglob("*.py") if ".git" not in p.parts]
    assert len(pys) > 15
    for p in pys:
        py_compile.compile(str(p), cfile=str(tmp_path / "x.pyc"), doraise=True)
    settings = (root / "acme_garden_club/settings.py").read_text()
    assert "ROOT_URLCONF = 'acme_garden_club.urls'" in settings
    assert "SITE_NAME = 'Acme Garden Club'" in settings
    assert "'django.middleware.locale.LocaleMiddleware'" in settings
    assert "acme_garden_club" in (root / "manage.py").read_text()
    assert "acme_garden_club.settings" in (root / "acme_garden_club/wsgi.py").read_text()
    assert (root / "acme_garden_club/__init__.py").is_file()


def test_foss_agents_and_verification_files(tmp_path):
    root = scaffold(tmp_path, "--author", "Jane Doe")
    files = set(tree(root))
    for expected in ("LICENSE", "CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "SECURITY.md", "AGENTS.md", "CLAUDE.md",
                     "README.md", ".gitignore", ".env.example", ".github/PULL_REQUEST_TEMPLATE.md",
                     ".github/ISSUE_TEMPLATE/bug_report.yml", ".github/ISSUE_TEMPLATE/feature_request.yml",
                     "scripts/visual_check.py", "bin/verify.sh", ".opskit/pack.yml"):
        assert expected in files, expected
    assert "Jane Doe" in (root / "LICENSE").read_text()
    for doc in ("AGENTS.md", "README.md", "CLAUDE.md"):
        assert "Events for a garden club" in (root / doc).read_text(), doc
    assert "@AGENTS.md" in (root / "CLAUDE.md").read_text()
    assert len((root / "CLAUDE.md").read_text().splitlines()) < 20  # thin
    assert os.access(root / "bin/verify.sh", os.X_OK) and os.access(root / "manage.py", os.X_OK)
    assert (root / "scripts/visual_check.py").read_bytes() == (REPO / "scripts/visual_check.py").read_bytes()
    assert "verify-shots/" in (root / ".gitignore").read_text()
    verify = (root / "bin/verify.sh").read_text()
    for needle in ("manage.py check", "makemigrations --check", "manage.py test", "seed_site", "visual_check.py",
                   "--mobile", "VERIFY RESULT: INCOMPLETE"):
        assert needle in verify, needle
    proc = subprocess.run(["bash", "-n", str(root / "bin/verify.sh")], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("lic,marker", [("MIT", "MIT License"), ("ISC", "ISC License"),
                                        ("BSD-3-Clause", "BSD 3-Clause"), ("Unlicense", "unencumbered")])
def test_licenses(tmp_path, lic, marker):
    root = scaffold(tmp_path, "--license", lic)
    assert marker in (root / "LICENSE").read_text()


def test_pack_yml_is_valid_and_references_real_files(tmp_path):
    root = scaffold(tmp_path, name="Acme Garden Club", purpose='Say "hi": events & news')
    text = (root / ".opskit/pack.yml").read_text()
    top = {}
    docs, in_docs = [], False
    for line in text.splitlines():
        if line.startswith("  - ") and in_docs:
            docs.append(line[4:].strip())
            continue
        in_docs = line.startswith("docs:")
        if re.match(r"^[a-z_]+:", line):
            k, _, v = line.partition(":")
            top[k] = v.strip()
    assert top["contract"] == "1"
    assert re.fullmatch(r"[a-z][a-z0-9-]*", top["name"]) and top["name"] == "acme-garden-club"
    assert top["data_classification"] in ("public", "internal", "client")
    assert top["sync"] in ("clone", "symlink")
    import json
    assert "Say \"hi\"" in json.loads(top["description"])  # JSON string == valid YAML scalar
    assert docs and all((root / d).is_file() for d in docs), docs
    try:
        import yaml  # optional extra check
    except ImportError:
        return
    assert yaml.safe_load(text)["name"] == "acme-garden-club"


def test_no_opskit_flag(tmp_path):
    root = scaffold(tmp_path, "--no-opskit")
    assert not (root / ".opskit").exists()


def test_scaffold_makes_git_repo_with_neutral_identity(tmp_path):
    root = scaffold(tmp_path)
    log = subprocess.run(["git", "-C", str(root), "log", "--format=%an|%B"], capture_output=True, text=True)
    assert log.returncode == 0 and "Initial Acme Garden Club site" in log.stdout
    assert "Co-Authored-By" not in log.stdout and "Claude" not in log.stdout
    tracked = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True).stdout
    assert "db.sqlite3" not in tracked and ".env\n" not in tracked


def test_no_asset_is_gitignored():
    """A file the scaffolder needs must not be silently dropped by the repo's own .gitignore
    (.env.example was: it passed locally and was missing from the committed PR)."""
    import shutil, subprocess
    repo = Path(__file__).resolve().parent.parent
    if shutil.which("git") is None or not (repo / ".git").exists():
        pytest.skip("not a git checkout")
    files = [p.relative_to(repo).as_posix() for p in (repo / "assets").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    out = subprocess.run(["git", "check-ignore", "--no-index", *files], cwd=repo, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"gitignored asset files: {out.stdout}"


# ---- playwright preflight ------------------------------------------------------------------

def cli_no_playwright(tmp_path, *args):
    """Run the CLI where neither PLAYWRIGHT_PYTHON nor python3 on PATH can import playwright."""
    empty = tmp_path / "emptybin"
    empty.mkdir(exist_ok=True)
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
           "PATH": str(empty), "PLAYWRIGHT_PYTHON": str(tmp_path / "no-such-python")}
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, env=env, timeout=120)


def test_preflight_missing_playwright_prints_notice_and_continues(tmp_path):
    proc = cli_no_playwright(tmp_path, "--name", "Pw Site", "--purpose", "p", "--parent-dir", str(tmp_path),
                             "--no-venv", "--yes")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "NOTICE: Playwright is not ready" in proc.stdout
    assert "INCOMPLETE" in proc.stdout
    assert "PLAYWRIGHT_PYTHON=/tmp/pw-venv/bin/python" in proc.stdout
    assert "playwright install chromium" in proc.stdout
    assert (tmp_path / "pw-site" / "bin" / "verify.sh").is_file()


def test_require_playwright_is_fatal_and_creates_nothing(tmp_path):
    proc = cli_no_playwright(tmp_path, "--name", "Pw Site", "--purpose", "p", "--parent-dir", str(tmp_path),
                             "--no-venv", "--yes", "--require-playwright")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "--require-playwright" in proc.stderr and "playwright install chromium" in proc.stderr
    assert not (tmp_path / "pw-site").exists()


def test_preflight_ok_when_playwright_and_chromium_present(tmp_path, monkeypatch):
    fake = tmp_path / "fakepy"
    fake.write_text("#!/bin/sh\n"
                    "case \"$2\" in *executable_path*) echo 1;; esac\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PLAYWRIGHT_PYTHON", str(fake))
    assert ns.playwright_preflight() == (True, [])


def test_preflight_reports_missing_chromium(tmp_path, monkeypatch):
    fake = tmp_path / "fakepy"
    fake.write_text("#!/bin/sh\ncase \"$2\" in *executable_path*) echo 0;; esac\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PLAYWRIGHT_PYTHON", str(fake))
    monkeypatch.setenv("PATH", str(tmp_path / "nothing"))
    ok, problems = ns.playwright_preflight()
    assert not ok and any("chromium is not installed" in p for p in problems)


# ---- debug toolbar switch ------------------------------------------------------------------

SITE_SRC = REPO / "assets" / "default-site"


def load_settings_and_urls(tmp_path, monkeypatch, debug, toolbar, toolbar_installed=True):
    """Import the settings fragment (plain Python) and evaluate the urls fragment against it, with
    stubs for django.conf/urls so no database or installed CMS is needed."""
    import types
    for k in ("DJANGO_DEBUG", "DJANGO_DEBUG_TOOLBAR", "DJANGO_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    if debug is not None:
        monkeypatch.setenv("DJANGO_DEBUG", debug)
    if toolbar is not None:
        monkeypatch.setenv("DJANGO_DEBUG_TOOLBAR", toolbar)
    monkeypatch.setenv("DJANGO_SECRET_KEY", "x")
    # The settings only enable the toolbar when the package is importable (it is a dev-only requirement).
    import importlib.util
    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: (
        object() if name == "debug_toolbar" and toolbar_installed else
        None if name == "debug_toolbar" else real_find_spec(name, *a, **k)))
    monkeypatch.syspath_prepend(str(SITE_SRC))
    sys.modules.pop("starter", None)
    sys.modules.pop("starter.constants", None)
    code = (SITE_SRC / "settings_fragment.py").read_text(encoding="utf-8")
    # Only the settings import of ImproperlyConfigured needs Django; stub it so the test stays offline.
    exc = types.ModuleType("django.core.exceptions")
    exc.ImproperlyConfigured = type("ImproperlyConfigured", (Exception,), {})
    for name, m in (("django", types.ModuleType("django")), ("django.core", types.ModuleType("django.core")),
                    ("django.core.exceptions", exc)):
        monkeypatch.setitem(sys.modules, name, m)
    mod = types.ModuleType("fake_settings")
    mod.__file__ = str(SITE_SRC / "settings_fragment.py")
    exec(compile(code, mod.__file__, "exec"), mod.__dict__)

    urls_code = (SITE_SRC / "urls_fragment.py").read_text(encoding="utf-8")
    stubs = {
        "django.conf": types.SimpleNamespace(settings=mod),
        "django.conf.urls.static": types.SimpleNamespace(static=lambda *a, **k: []),
        "django.contrib": types.SimpleNamespace(admin=types.SimpleNamespace(site=types.SimpleNamespace(urls=None))),
        "django.urls": types.SimpleNamespace(include=lambda x: ("include", x), path=lambda r, v, name=None: (r, v),
                                         re_path=lambda r, v, kw=None: (r, v)),
    }
    mod.MEDIA_URL, mod.MEDIA_ROOT = "/media/", "m"
    ns_ = {}
    prelude = "\n".join(l for l in urls_code.splitlines() if not l.startswith(("from django", "import django", "from .")))
    ns_.update(settings=mod, static=stubs["django.conf.urls.static"].static, admin=stubs["django.contrib"].admin,
               include=stubs["django.urls"].include, path=stubs["django.urls"].path,
               re_path=stubs["django.urls"].re_path, serve_media=None, health=None)
    exec(compile(prelude, "urls_fragment", "exec"), ns_)
    mod.URLPATTERNS = ns_["urlpatterns"]
    return mod


def toolbar_state(mod):
    app = "debug_toolbar" in mod.INSTALLED_APPS
    mw = "debug_toolbar.middleware.DebugToolbarMiddleware" in mod.MIDDLEWARE
    url = any(r == "__debug__/" for r, _ in mod.URLPATTERNS)
    return app, mw, url


@pytest.mark.parametrize("debug,toolbar,expected", [
    ("1", None, True),
    ("1", "1", True),
    ("1", "anything", True),
    ("1", "0", False),
    ("1", "false", False),
    ("1", "No", False),
    ("1", "OFF", False),
    (None, None, False),
    (None, "1", False),
])
def test_debug_toolbar_switch_is_consistent(tmp_path, monkeypatch, debug, toolbar, expected):
    mod = load_settings_and_urls(tmp_path, monkeypatch, debug, toolbar)
    assert toolbar_state(mod) == (expected, expected, expected)
    if expected:
        assert mod.MIDDLEWARE[0] == "cms.middleware.utils.ApphookReloadMiddleware"
        assert mod.MIDDLEWARE[1] == "debug_toolbar.middleware.DebugToolbarMiddleware"
        assert mod.INTERNAL_IPS
    else:
        assert not hasattr(mod, "INTERNAL_IPS")


def test_debug_toolbar_needs_the_dev_package(tmp_path, monkeypatch):
    """DEBUG without django-debug-toolbar installed (production requirements only) must not enable it."""
    mod = load_settings_and_urls(tmp_path, monkeypatch, "1", None, toolbar_installed=False)
    assert toolbar_state(mod) == (False, False, False)


# ---- verify.sh content ---------------------------------------------------------------------

def test_verify_sh_disables_toolbar_and_prints_coverage(tmp_path):
    root = scaffold(tmp_path)
    text = (root / "bin" / "verify.sh").read_text()
    assert "DJANGO_DEBUG_TOOLBAR=0" in text and "runserver" in text
    run_line = next(l for l in text.splitlines() if "runserver" in l and "$PORT" in l)
    assert "DJANGO_DEBUG_TOOLBAR=0" in run_line
    for step in ("1/5 manage.py check", "2/5 makemigrations", "3/5 tests", "4/5 seed idempotency",
                 "5/5 visual check"):
        assert step in text
    assert "horizontal overflow" in text and "NOT checked" in text
    assert "/tmp/pw-venv" in text
    subprocess.run(["bash", "-n", str(root / "bin" / "verify.sh")], check=True)


def test_generated_readme_documents_treebeard_and_debug_toolbar(tmp_path):
    readme = (scaffold(tmp_path) / "README.md").read_text()
    assert "treebeard.E001" in readme and "harmless" in readme
    assert "DJANGO_DEBUG_TOOLBAR=0" in readme
    assert "debug-toolbar handle" in readme


def test_overflow_claim_matches_script():
    src = (REPO / "scripts" / "visual_check.py").read_text()
    assert "scrollWidth" in src and "clientWidth" in src


# ---- Docker + PostgreSQL support ------------------------------------------------------------

DOCKER_FILES = ["Dockerfile", "docker-compose.yml", "docker-compose.dev.yml", "docker/entrypoint.sh",
                "docker/dev-entrypoint.sh", ".dockerignore", "bin/docker-up.sh", "bin/docker-down.sh",
                "bin/docker-env.sh", "bin/docker-backup.sh", "bin/docker-restore.sh", "bin/dev-up.sh",
                "bin/dev-down.sh", "bin/pin-images.sh", "bin/pin_images.py", "starter/tests_pins.py"]
SHELL_SCRIPTS = ["docker/entrypoint.sh", "docker/dev-entrypoint.sh", "bin/docker-up.sh", "bin/docker-down.sh",
                 "bin/docker-env.sh", "bin/docker-backup.sh", "bin/docker-restore.sh", "bin/dev-up.sh",
                 "bin/dev-down.sh", "bin/pin-images.sh", "bin/release.sh"]
# Kept by --no-docker: the settings, requirements-dev.txt (debug toolbar for the local venv), the release script,
# the changelog and the map/video templates are not container files.
ALWAYS_FILES = ["requirements.txt", "requirements-dev.txt", "bin/release.sh", "CHANGELOG.md", "bin/verify.sh",
                "static/js/googlemap-guard.js", "templates/djangocms_googlemap/default/map.html",
                "templates/djangocms_video/default/video_player.html", "starter/tests_release.py"]


def test_docker_files_in_plan_and_on_disk_by_default(tmp_path):
    plan = cli("--name", "Acme Garden Club", "--purpose", "x", "--parent-dir", str(tmp_path), "--dry-run")
    assert plan.returncode == 0
    assert "docker=yes" in plan.stdout
    root = scaffold(tmp_path)
    files = tree(root)
    for rel in DOCKER_FILES + ["acme_garden_club/health.py", "starter/tests_docker.py",
                               "starter/management/commands/seed.py"]:
        assert rel in files, rel
        if rel in DOCKER_FILES:
            assert f"write {rel}" in plan.stdout, rel
    assert (root / "docker-compose.yml").read_text().startswith("name: acme_garden_club")
    assert "gunicorn acme_garden_club.wsgi:application" in (root / "docker/entrypoint.sh").read_text()
    for rel in ("Dockerfile", "docker-compose.yml", "docker/entrypoint.sh", ".dockerignore", "bin/docker-env.sh",
                "starter/tests_docker.py", ".env.example"):
        assert not any(p in (root / rel).read_text() for p in PLACEHOLDERS), rel


def test_no_docker_omits_docker_files_but_keeps_settings(tmp_path):
    root = scaffold(tmp_path, "--no-docker")
    files = tree(root)
    for rel in DOCKER_FILES:
        assert rel not in files, rel
    assert not (root / "docker").exists()
    assert "bin/verify.sh" in files and "acme_garden_club/settings.py" in files
    readme = (root / "README.md").read_text() + (root / "AGENTS.md").read_text()
    assert "Docker" not in readme and "{{" not in readme
    plan = cli("--name", "Other Site", "--purpose", "x", "--parent-dir", str(tmp_path), "--dry-run",
               "--no-docker")
    assert "docker=no" in plan.stdout and "Dockerfile" not in plan.stdout
    for rel in DOCKER_FILES:
        assert f"write {rel}" not in plan.stdout, rel


def test_docker_docs_in_generated_readme_and_agents(tmp_path):
    root = scaffold(tmp_path)
    readme, agents = (root / "README.md").read_text(), (root / "AGENTS.md").read_text()
    for needle in ("## Docker + PostgreSQL", "bin/docker-up.sh", "APP_PORT", "8889", "DJANGO_CSRF_TRUSTED_ORIGINS",
                   "manage.py seed"):
        assert needle in readme, needle
    assert "## Docker + PostgreSQL" in agents and "volume prune" in agents
    assert "{{" not in readme and "{{" not in agents


def test_shell_scripts_executable_and_parse(tmp_path):
    root = scaffold(tmp_path)
    for rel in SHELL_SCRIPTS + ["bin/verify.sh"]:
        assert os.access(root / rel, os.X_OK), rel
        subprocess.run(["bash", "-n", str(root / rel)], check=True)
    assert os.access(root / "bin/pin_images.py", os.X_OK)
    # the committed tree keeps the executable bits (a fresh clone must still run the scripts)
    modes = subprocess.run(["git", "-C", str(root), "ls-files", "-s", *SHELL_SCRIPTS], capture_output=True, text=True).stdout
    assert modes.count("100755") == len(SHELL_SCRIPTS), modes


def test_hardening_files_ship_by_default_and_are_listed_in_the_plan(tmp_path):
    plan = cli("--name", "Acme Garden Club", "--purpose", "x", "--parent-dir", str(tmp_path), "--dry-run")
    for rel in DOCKER_FILES + ALWAYS_FILES:
        assert f"write {rel}" in plan.stdout, rel
    root = scaffold(tmp_path)
    files = set(tree(root))
    for rel in DOCKER_FILES + ALWAYS_FILES + [".env.example"]:
        assert rel in files, rel


def test_no_docker_keeps_non_container_hardening_files(tmp_path):
    root = scaffold(tmp_path, "--no-docker")
    files = set(tree(root))
    for rel in ALWAYS_FILES:
        assert rel in files, rel
    for rel in DOCKER_FILES:
        assert rel not in files, rel
    for rel in ("bin/release.sh", "bin/verify.sh"):
        subprocess.run(["bash", "-n", str(root / rel)], check=True)
    assert "{{" not in (root / "CONTRIBUTING.md").read_text()


def test_requirements_split_and_dockerfile_stages(tmp_path):
    root = scaffold(tmp_path)
    assert "debug-toolbar" not in (root / "requirements.txt").read_text()
    dev = (root / "requirements-dev.txt").read_text()
    assert "-r requirements.txt" in dev and "django-debug-toolbar==" in dev
    assert "docutils==" in (root / "requirements.txt").read_text()  # /admin/docs/ is enabled
    docker = (root / "Dockerfile").read_text()
    stages = re.findall(r"^FROM .* AS (\w+)$", docker, re.M)
    assert stages == ["base", "dev", "production"]


def test_dev_compose_is_standalone_loopback_only_and_prod_has_no_dev_settings(tmp_path):
    root = scaffold(tmp_path)
    dev = (root / "docker-compose.dev.yml").read_text()
    prod = (root / "docker-compose.yml").read_text()
    assert "name: acme_garden_club-dev" in dev and "8880" in dev
    assert "target: dev" in dev and ".:/app" in dev and "runserver" in (root / "docker/dev-entrypoint.sh").read_text()
    for port in re.findall(r'^\s*-\s*"([^"]*:\d+:\d+)"', dev, re.M):
        assert port.startswith("127.0.0.1:"), port
    assert "image: ${APP_IMAGE:-acme_garden_club}:${APP_VERSION:-latest}" in prod
    assert "target: production" in prod and "DJANGO_DEBUG: \"1\"" not in prod and "- .:/app" not in prod
    assert "dev-only-password" not in prod


def test_images_in_generated_files_are_pinned_by_digest(tmp_path):
    root = scaffold(tmp_path)
    for rel in ("Dockerfile", "docker-compose.yml", "docker-compose.dev.yml"):
        for line in (root / rel).read_text().splitlines():
            m = re.match(r"^\s*(?:FROM\s+(\S+)|image:\s*(\S+))", line)
            ref = (m.group(1) or m.group(2)) if m else None
            if ref and "$" not in ref and ref not in ("base",):
                assert re.search(r"@sha256:[0-9a-f]{64}$", ref), f"{rel}: {ref}"
                assert re.search(r":[\w.-]+@sha256", ref), f"{rel}: tag must stay readable: {ref}"


def test_settings_fragment_hardening_switches():
    s = (SITE_SRC / "settings_fragment.py").read_text()
    for needle in ("DJANGO_CACHE", "DatabaseCache", "django_cache", "DJANGO_CMS_CACHE", "SESSION_COOKIE_SECURE",
                   "CSRF_COOKIE_SECURE", "LANGUAGE_COOKIE_SECURE", "DJANGO_HSTS_SECONDS", "DJANGO_HSTS_INCLUDE_SUBDOMAINS",
                   "DJANGO_SSL_REDIRECT", "SECURE_REDIRECT_EXEMPT", "FILER_STORAGES", "PrivateFileSystemStorage",
                   "excluded_plugins", "GoogleMapPlugin", "'127.0.0.1'"):
        assert needle in s, needle
    assert "filer_private" in (SITE_SRC / "urls_fragment.py").read_text()


def test_dropdown_toggle_is_a_button():
    menu = (SITE_SRC / "templates" / "menu" / "menu.html").read_text()
    assert '<button type="button" class="nav-link dropdown-toggle' in menu
    assert 'role="button"' not in menu


def test_generated_docs_cover_the_hardening_topics(tmp_path):
    root = scaffold(tmp_path)
    readme = (root / "README.md").read_text()
    for needle in ("bin/docker-backup.sh", "bin/docker-restore.sh", "--wipe", "ON_ERROR_STOP", "bin/dev-up.sh", "8880",
                   "bin/pin-images.sh", "bin/release.sh", "APP_BIND=0.0.0.0", "DJANGO_CACHE", "--first-run-only",
                   "CREATE_VERSIONS", "requirements-dev.txt"):
        assert needle in readme, needle
    contributing = (root / "CONTRIBUTING.md").read_text()
    assert "refreshed with every `vX.Y.Z` release" in contributing and "{{" not in contributing
    assert "refreshed with each `vX.Y.Z` release" in (root / "AGENTS.md").read_text()
    env = (root / ".env.example").read_text()
    for needle in ("DJANGO_ALLOWED_HOSTS=example.org,localhost,127.0.0.1", "CREATE_VERSIONS_USER", "DJANGO_CACHE",
                   "DJANGO_HSTS_SECONDS", "DEV_PORT", "APP_VERSION", "SEED_ON_START"):
        assert needle in env, needle


def test_verify_sh_cd_has_exit_guard(tmp_path):
    text = (scaffold(tmp_path) / "bin" / "verify.sh").read_text()
    assert 'cd "$(dirname "$0")/.." || exit 1' in text


def test_release_script_dry_run_and_real_run_in_a_scaffold(tmp_path):
    """The generated bin/release.sh works in a freshly scaffolded git repo (checks and pins stubbed)."""
    root = scaffold(tmp_path)
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
           "RELEASE_PIN_CMD": "true", "RELEASE_TEST_CMD": "true",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com"}
    dry = subprocess.run(["bash", "bin/release.sh", "v0.1.0", "--dry-run"], cwd=root, env=env, capture_output=True, text=True)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert not (root / "VERSION").exists()
    real = subprocess.run(["bash", "bin/release.sh", "v0.1.0"], cwd=root, env=env, capture_output=True, text=True)
    assert real.returncode == 0, real.stdout + real.stderr
    assert (root / "VERSION").read_text() == "0.1.0\n"
    assert "## [0.1.0] -" in (root / "CHANGELOG.md").read_text()
    assert "git push origin v0.1.0" in real.stdout
    tags = subprocess.run(["git", "-C", str(root), "tag"], capture_output=True, text=True).stdout
    assert tags.split() == ["v0.1.0"]


def test_docker_env_script_makes_private_env_and_never_overwrites(tmp_path):
    root = scaffold(tmp_path)
    run = lambda: subprocess.run([str(root / "bin/docker-env.sh")], capture_output=True, text=True, check=True)
    out = run().stdout
    env = (root / ".env").read_text()
    assert "DB_NAME=acme_garden_club" in env and "DB_PASSWORD=" in env and "DJANGO_SECRET_KEY=" in env
    assert (root / ".env").stat().st_mode & 0o777 == 0o600
    secret = next(l for l in env.splitlines() if l.startswith("DB_PASSWORD=")).split("=", 1)[1]
    assert secret and secret not in out
    (root / ".env").write_text("KEEP=1\n")
    assert "already exists" in run().stdout and (root / ".env").read_text() == "KEEP=1\n"


@pytest.mark.skipif(__import__("shutil").which("docker") is None, reason="docker not installed")
def test_compose_file_is_valid(tmp_path):
    root = scaffold(tmp_path)
    env = {**os.environ, "DB_PASSWORD": "x", "DJANGO_SECRET_KEY": "x", "APP_PORT": "8891"}
    proc = subprocess.run(["docker", "compose", "config"], cwd=root, env=env, capture_output=True, text=True)
    if proc.returncode != 0 and "compose" in proc.stderr and "not a docker command" in proc.stderr:
        pytest.skip("docker compose plugin not installed")
    assert proc.returncode == 0, proc.stderr
    assert "http://localhost:8891" in proc.stdout  # CSRF default follows APP_PORT
    assert "postgres:16-alpine" in proc.stdout


@pytest.mark.skipif(__import__("shutil").which("docker") is None, reason="docker not installed")
def test_dev_compose_file_is_valid(tmp_path):
    root = scaffold(tmp_path)
    env = {**os.environ, "DEV_PORT": "8898"}
    proc = subprocess.run(["docker", "compose", "-f", "docker-compose.dev.yml", "config"], cwd=root, env=env,
                          capture_output=True, text=True)
    if proc.returncode != 0 and "not a docker command" in proc.stderr:
        pytest.skip("docker compose plugin not installed")
    assert proc.returncode == 0, proc.stderr
    assert "name: acme_garden_club-dev" in proc.stdout
    assert "127.0.0.1" in proc.stdout and "8898" in proc.stdout


def test_requirements_pin_docker_dependencies():
    reqs = (SITE_SRC / "requirements.txt").read_text()
    for pkg in ("psycopg[binary]==", "gunicorn==", "whitenoise=="):
        assert pkg in reqs, pkg


def test_settings_fragment_docker_switches():
    s = (SITE_SRC / "settings_fragment.py").read_text()
    assert "DB_ENGINE" in s and "django.db.backends.sqlite3" in s and "django.db.backends.postgresql" in s
    mw = s[s.index("MIDDLEWARE = ["):]
    order = [mw.index(x) for x in ("ApphookReloadMiddleware", "SecurityMiddleware", "WhiteNoiseMiddleware",
                                   "SessionMiddleware")]
    assert order == sorted(order)
    assert "DJANGO_SERVE_MEDIA" in s and "CompressedStaticFilesStorage" in s


def test_dry_run_still_writes_nothing_and_no_venv_flags_work(tmp_path):
    proc = cli("--name", "Acme", "--purpose", "x", "--parent-dir", str(tmp_path), "--no-venv", "--skip-install",
               "--dry-run")
    assert proc.returncode == 0 and list(tmp_path.iterdir()) == []


# --- interactive prompts re-ask instead of failing after all questions (D6) ---

def _interactive(monkeypatch, answers):
    it = iter(answers)
    asked = []

    def fake_input(label=""):
        asked.append(label)
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    return asked


def test_interactive_reprompts_bad_name_then_good(monkeypatch, capsys):
    asked = _interactive(monkeypatch, ["", "../evil", "9lives", "Good Site", "A site for tests"])
    args = ns.build_parser().parse_args([])
    assert ns.resolve_inputs(args) is True
    assert args.name == "Good Site" and args.purpose == "A site for tests"
    # the name was validated immediately: three name prompts before the purpose prompt
    assert [a.startswith("Site name") for a in asked] == [True, True, True, True, False]
    err = capsys.readouterr().err
    assert err.count("Not accepted") == 3 and "Please try again" in err


def test_interactive_reprompts_empty_purpose(monkeypatch, capsys):
    asked = _interactive(monkeypatch, ["Good Site", "", "   ", "Real purpose"])
    args = ns.build_parser().parse_args([])
    ns.resolve_inputs(args)
    assert args.purpose == "Real purpose"
    assert capsys.readouterr().err.count("the purpose must not be empty") == 2


def test_interactive_eof_still_exits_usage_error(monkeypatch):
    _interactive(monkeypatch, ["", ""])  # then EOF
    args = ns.build_parser().parse_args([])
    with pytest.raises(ns.UsageError):
        ns.resolve_inputs(args)


def test_non_tty_missing_args_still_usage_error(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    args = ns.build_parser().parse_args([])
    with pytest.raises(ns.UsageError):
        ns.resolve_inputs(args)


def test_container_file_tests_skip_without_docker_files():
    """A --no-docker site still ships starter/tests_docker.py and tests_release.py (the behaviour tests apply
    either way), so every class that reads container files must skip itself when the Dockerfile is absent
    (found: verify.sh ended FAIL)."""
    site = REPO / "assets" / "default-site" / "starter"
    for fname in ("tests_docker.py", "tests_release.py"):
        text = (site / fname).read_text()
        assert "docker_only = unittest.skipUnless((BASE / " in text.replace('"Dockerfile"', "'Dockerfile'") or \
            "docker_only = unittest.skipUnless((BASE / \"Dockerfile\")" in text, fname
    text = (site / "tests_docker.py").read_text()
    for cls in ("ContainerFilesTests", "ComposeWiringTests", "DockerEnvScriptTests"):
        assert f"@docker_only\nclass {cls}" in text, cls
    assert "@docker_only\nclass ComposeSplitTests" in (site / "tests_release.py").read_text()
    assert "SkipTest" in (site / "tests_pins.py").read_text()  # whole module skips without bin/pin_images.py
