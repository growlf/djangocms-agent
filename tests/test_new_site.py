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


def load_settings_and_urls(tmp_path, monkeypatch, debug, toolbar):
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
        "django.urls": types.SimpleNamespace(include=lambda x: ("include", x), path=lambda r, v: (r, v)),
    }
    mod.MEDIA_URL, mod.MEDIA_ROOT = "/media/", "m"
    ns_ = {}
    prelude = "\n".join(l for l in urls_code.splitlines() if not l.startswith(("from django", "import django")))
    ns_.update(settings=mod, static=stubs["django.conf.urls.static"].static, admin=stubs["django.contrib"].admin,
               include=stubs["django.urls"].include, path=stubs["django.urls"].path)
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
