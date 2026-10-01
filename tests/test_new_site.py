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
