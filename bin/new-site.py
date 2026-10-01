#!/usr/bin/env python3
"""Scaffold a complete DjangoCMS 5 site: the default site plus FOSS files, OpsKit manifest and verification.

Usage:
    bin/new-site.py --name "Acme Garden Club" --purpose "Member news and events for a garden club" \\
                    [--site-name NAME] [--parent-dir DIR] [--license MIT] [--author NAME]
                    [--no-venv | --skip-install] [--no-opskit] [--dry-run] [--yes]

NAME and PURPOSE come from the human. When they are missing the script prompts if stdin is a terminal
and otherwise exits with code 2: an agent must ask the person, never invent them.

What it does, in order: validate -> create <parent-dir>/<slug>/ -> write the default site (assets/default-site
with __PROJECT_NAME__ / __SITE_NAME__ substituted in contents and paths), the project package files
(__init__, wsgi, asgi), FOSS files, AGENTS.md + CLAUDE.md, README, .opskit/pack.yml, scripts/visual_check.py,
bin/verify.sh -> venv + pip install -> migrate -> admin superuser (random password, printed once, never
stored) -> seed_pages + seed_site -> git init + first commit.  It never overwrites an existing file and
refuses a non-empty target directory.  It never calls any `opskit` command: OpsKit integration is only the
manifest file.

Exit codes: 0 success; 1 a build step failed (the partially built project is left in place and the failing
step is named); 2 usage or validation error (missing name/purpose in a non-interactive run, invalid name,
unsupported license, target directory exists and is not empty).
Python 3.12+, standard library only.
"""
import argparse
import json
import keyword
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import unicodedata
from datetime import date
from pathlib import Path

EXIT_OK, EXIT_STEP_FAILED, EXIT_USAGE = 0, 1, 2

# bin/ may be the repo's bin/ or a copy of it inside an installed skill; assets/ and scripts/ sit next to it
# in both layouts (skills/djangocms-agent/{bin,assets,scripts} are symlinks or copies of the repo directories).
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE = ROOT / "assets" / "default-site"
FOSS = ROOT / "assets" / "foss"
VISUAL_CHECK = ROOT / "scripts" / "visual_check.py"

LICENSES = ("MIT", "ISC", "BSD-3-Clause", "Unlicense")
# Names a project package must not take: they would shadow an installed package or a bundled app.
RESERVED_PACKAGES = {
    "django", "cms", "menus", "sekizai", "treebeard", "filer", "starter", "test", "tests", "site", "sites",
    "admin", "static", "templates", "media", "venv", "scripts", "bin", "config", "settings", "manage",
    "easy_thumbnails", "debug_toolbar", "pip", "setuptools", "wheel", "sys", "os", "json", "logging",
    "email", "http", "html", "string", "types", "typing", "random", "time", "datetime", "collections",
}
TOKEN_RE = re.compile(r"\{\{([A-Z_]+)\}\}")
SKIP_DIRS = {"__pycache__"}
SKIP_SUBST_PREFIXES = ("static/vendor/",)  # vendored third-party files are copied byte for byte
# default-site files that are not copied verbatim
SPECIAL = {"README.md", "settings_fragment.py", "urls_fragment.py", "gitignore.template"}


class UsageError(Exception):
    pass


class StepError(Exception):
    pass


# --------------------------------------------------------------------------- names

def derive_names(name):
    """Return (slug, package) for a human site name, or raise UsageError.

    slug is the safe directory name and the OpsKit manifest name (lowercase letters, digits, hyphens);
    package is the Python package name for settings/urls (the slug with underscores).
    """
    if not isinstance(name, str) or not name.strip():
        raise UsageError("--name must not be empty")
    name = name.strip()
    if len(name) > 64:
        raise UsageError("--name is too long (max 64 characters)")
    if any(ch in name for ch in "/\\\0") or name.startswith(".") or ".." in name:
        raise UsageError(f"--name {name!r} must not contain path separators, NUL or '..' and must not start with '.'")
    if any(unicodedata.category(ch).startswith("C") for ch in name):
        raise UsageError("--name must not contain control characters")
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    if not slug:
        raise UsageError(f"--name {name!r} has no usable letters or digits (use ASCII letters/digits)")
    if not slug[0].isalpha():
        raise UsageError(f"--name {name!r} must start with a letter (the Python package cannot start with a digit)")
    package = slug.replace("-", "_")
    if not package.isidentifier() or keyword.iskeyword(package):
        raise UsageError(f"--name {name!r} gives {package!r}, which is not a valid Python package name")
    if package in RESERVED_PACKAGES or package.startswith(("django_", "djangocms_")):
        raise UsageError(f"--name {name!r} gives package {package!r}, which would shadow an installed module; choose another")
    return slug, package


def clean_line(text, field, limit):
    text = " ".join(str(text).split())
    if not text:
        raise UsageError(f"{field} must not be empty")
    if any(unicodedata.category(ch).startswith("C") for ch in text):
        raise UsageError(f"{field} must not contain control characters")
    if len(text) > limit:
        raise UsageError(f"{field} is too long (max {limit} characters)")
    return text


def default_site_name(name):
    name = " ".join(name.split())
    return name.title() if name == name.lower() else name


def py_str(value):
    """Escape for inclusion inside a single-quoted Python string literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


# --------------------------------------------------------------------------- templating

def render(text, variables):
    def sub(m):
        key = m.group(1)
        if key not in variables:
            raise StepError(f"template uses unknown variable {{{{{key}}}}}")
        return variables[key]
    return TOKEN_RE.sub(sub, text)


def substitute_site_tokens(text, package, site_name, python_literal):
    site = py_str(site_name) if python_literal else site_name
    return text.replace("__PROJECT_NAME__", package).replace("__SITE_NAME__", site)


def read_asset_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


# --------------------------------------------------------------------------- plan

class Plan:
    """Ordered list of (relative path, kind, payload, executable). kind: text | copy."""

    def __init__(self):
        self.items = []
        self.seen = set()

    def add(self, rel, kind, payload, executable=False):
        rel = str(rel)
        if rel in self.seen:
            raise StepError(f"plan would write {rel} twice")
        self.seen.add(rel)
        self.items.append((rel, kind, payload, executable))

    def paths(self):
        return [i[0] for i in self.items]


WSGI = '''"""WSGI config for {package}."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "{package}.settings")

application = get_wsgi_application()
'''

ASGI = '''"""ASGI config for {package}."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "{package}.settings")

application = get_asgi_application()
'''


def build_plan(ctx):
    package, site_name = ctx["package"], ctx["site_name"]
    plan = Plan()

    # 1. default site, with tokens substituted in paths and contents
    for src in sorted(DEFAULT_SITE.rglob("*")):
        if not src.is_file() or SKIP_DIRS & set(src.parts):
            continue
        rel = src.relative_to(DEFAULT_SITE).as_posix()
        if rel in SPECIAL or rel.endswith(".pyc"):
            continue
        dest = substitute_site_tokens(rel, package, site_name, False)
        text = None if rel.startswith(SKIP_SUBST_PREFIXES) else read_asset_text(src)
        executable = bool(src.stat().st_mode & 0o111) or rel == "manage.py"
        if text is None:
            plan.add(dest, "copy", src, executable)
        else:
            plan.add(dest, "text", substitute_site_tokens(text, package, site_name, dest.endswith(".py")), executable)
    for frag, dest in (("settings_fragment.py", f"{package}/settings.py"), ("urls_fragment.py", f"{package}/urls.py")):
        text = (DEFAULT_SITE / frag).read_text(encoding="utf-8")
        plan.add(dest, "text", substitute_site_tokens(text, package, site_name, True))
    plan.add(".gitignore", "text", (DEFAULT_SITE / "gitignore.template").read_text(encoding="utf-8"))

    # 2. project package files (what `django-admin startproject` writes besides settings/urls)
    plan.add(f"{package}/__init__.py", "text", "")
    plan.add(f"{package}/wsgi.py", "text", WSGI.format(package=package))
    plan.add(f"{package}/asgi.py", "text", ASGI.format(package=package))

    # 3. FOSS files, agent files, README
    v = ctx["vars"]
    lic = FOSS / "licenses" / f"{ctx['license']}.tmpl"
    plan.add("LICENSE", "text", render(lic.read_text(encoding="utf-8"), v))
    for name in ("CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "SECURITY.md", "AGENTS.md", "CLAUDE.md", "README.md"):
        plan.add(name, "text", render((FOSS / f"{name}.tmpl").read_text(encoding="utf-8"), v))
    plan.add(".github/PULL_REQUEST_TEMPLATE.md", "text",
             (FOSS / "github/PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8"))
    for issue in sorted((FOSS / "github/ISSUE_TEMPLATE").glob("*.yml")):
        plan.add(f".github/ISSUE_TEMPLATE/{issue.name}", "text", issue.read_text(encoding="utf-8"))

    # 4. verification tooling
    plan.add("scripts/visual_check.py", "copy", VISUAL_CHECK, True)
    plan.add("bin/verify.sh", "text", render((FOSS / "verify.sh.tmpl").read_text(encoding="utf-8"), v), True)

    # 5. OpsKit manifest (a file only; no opskit command is ever run)
    if ctx["opskit"]:
        plan.add(".opskit/pack.yml", "text", pack_yml(ctx, plan.paths()))
    return plan


def pack_yml(ctx, planned):
    """OpsKit member manifest (contract 1), modelled on this repo's .opskit/pack.yml.

    Values are written as JSON strings, which are valid YAML scalars, so no value can break the file.
    data_classification is `internal` because the site's content is unknown; change it deliberately.
    `sync: symlink` because a fresh site has no git remote yet (set `sync: clone` and `url:` once it has one).
    """
    docs = [p for p in ("README.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md") if p in planned]
    lines = [
        "contract: 1",
        f"name: {ctx['slug']}",
        f"description: {json.dumps('DjangoCMS site: ' + ctx['purpose'])}",
        "data_classification: internal",
        "sync: symlink",
        "agents: []",
        "skills: []",
        "docs:",
        *[f"  - {d}" for d in docs],
        "trust:",
        "  bash: ask",
        "  tool_deny: []",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- writing

def write_plan(plan, target):
    root = target.resolve()
    for rel, kind, payload, executable in plan.items:
        dest = target / rel
        if root not in dest.resolve().parents:
            raise StepError(f"refusing to write outside the project directory: {rel}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if kind == "copy":
                with open(dest, "xb") as fh, open(payload, "rb") as src:
                    shutil.copyfileobj(src, fh)
            else:
                with open(dest, "x", encoding="utf-8", newline="\n") as fh:
                    fh.write(payload)
        except FileExistsError:
            raise StepError(f"{rel} already exists; refusing to overwrite")
        if executable:
            dest.chmod(dest.stat().st_mode | 0o755)


# --------------------------------------------------------------------------- steps

def run(cmd, cwd, env=None, step=""):
    shown = " ".join(str(c) for c in cmd)
    print(f"  $ {shown}", flush=True)
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        tail = "\n".join(proc.stdout.splitlines()[-25:])
        raise StepError(f"step '{step or shown}' failed (exit {proc.returncode}):\n{tail}")
    return proc.stdout


def free_port(start=8010, end=8099):
    for port in range(start, end):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def git_config(key):
    try:
        out = subprocess.run(["git", "config", "--get", key], capture_output=True, text=True, timeout=10)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def git_commit(target, site_name):
    if shutil.which("git") is None:
        print("  git not found: skipped git init (project files are in place)")
        return
    run(["git", "init", "-q", "-b", "main"], target, step="git init")
    run(["git", "add", "-A"], target, step="git add")
    ident = []
    if not (git_config("user.name") and git_config("user.email")):
        ident = ["-c", "user.name=site-scaffold", "-c", "user.email=site-scaffold@localhost"]
        print("  git user.name/user.email not set: the first commit uses the neutral identity 'site-scaffold' "
              "(fix later with `git commit --amend --reset-author` after setting your own)")
    run(["git", *ident, "-c", "commit.gpgsign=false", "commit", "-q", "--no-verify", "-m",
         f"Initial {site_name} site from the djangocms-agent default site"], target, step="git commit")


def build_project(ctx, target):
    """Run everything after the files are written. Returns the admin password (or None)."""
    password = None
    if ctx["install"]:
        print("== virtualenv and dependencies (this downloads packages)")
        run([sys.executable, "-m", "venv", "venv"], target, step="create venv")
        vpy = str(target / "venv" / "bin" / "python")
        run([vpy, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-r", "requirements.txt"],
            target, step="pip install -r requirements.txt")
        env = {**os.environ, "DJANGO_DEBUG": "1", "DJANGO_SECRET_KEY": secrets.token_urlsafe(32)}
        manage = [vpy, "manage.py"]
        print("== database, admin user, seed content")
        run([*manage, "check"], target, env, "manage.py check")
        run([*manage, "migrate", "--noinput"], target, env, "migrate")
        password = secrets.token_urlsafe(16)
        env_su = {**env, "DJANGO_SUPERUSER_USERNAME": "admin", "DJANGO_SUPERUSER_PASSWORD": password,
                  "DJANGO_SUPERUSER_EMAIL": "admin@localhost"}
        run([*manage, "createsuperuser", "--noinput"], target, env_su, "createsuperuser")
        # Fresh database: seeding publishes through versioning, so `create_versions` is not needed here.
        run([*manage, "seed_pages"], target, env, "seed_pages")
        run([*manage, "seed_site"], target, env, "seed_site")
    print("== git")
    git_commit(target, ctx["site_name"])
    return password


def print_plan(plan, target, ctx):
    print(f"Plan for {target}")
    print(f"  name={ctx['name']!r} slug={ctx['slug']} package={ctx['package']} site name={ctx['site_name']!r} "
          f"license={ctx['license']} opskit manifest={'yes' if ctx['opskit'] else 'no'}")
    vendor = 0
    for rel, _kind, _payload, _exe in plan.items:
        if rel.startswith("static/vendor/"):
            vendor += 1
            continue
        print(f"  write {rel}")
    print(f"  write {vendor} vendored static file(s) under static/vendor/")
    if ctx["install"]:
        print("  then: venv + pip install -r requirements.txt, migrate, admin superuser (random password), "
              "seed_pages, seed_site")
    else:
        print("  then: (venv, install, migrate and seed skipped by --no-venv/--skip-install)")
    print("  then: git init + first commit")


# --------------------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(
        description="Scaffold a DjangoCMS 5 default site. Exit codes: 0 ok, 1 build step failed, 2 usage error.")
    p.add_argument("--name", help="site name given by the human, e.g. 'Acme Garden Club' (directory/package are derived)")
    p.add_argument("--purpose", help="general purpose of the site, given by the human")
    p.add_argument("--site-name", help="display name for navbar/title (default: derived from --name)")
    p.add_argument("--parent-dir", default=".", help="directory in which the project folder is created (default: cwd)")
    p.add_argument("--license", default="MIT", help=f"one of: {', '.join(LICENSES)} (default MIT)")
    p.add_argument("--author", help="copyright holder (default: git user.name, else 'The <site> contributors')")
    p.add_argument("--no-venv", "--skip-install", dest="no_venv", action="store_true",
                   help="write files and git init only: no venv, pip install, migrate or seed")
    p.add_argument("--no-opskit", action="store_true", help="do not write .opskit/pack.yml")
    p.add_argument("--dry-run", action="store_true", help="print the file plan; touch nothing")
    p.add_argument("--yes", "-y", action="store_true", help="skip the confirmation asked after interactive prompts")
    return p


def prompt(label):
    try:
        return input(f"{label}: ").strip()
    except EOFError:
        raise UsageError(f"no answer given for {label}")


def resolve_inputs(args):
    """Fill in name/purpose interactively when possible. Returns True if the human was prompted."""
    missing = [f for f in ("name", "purpose") if not getattr(args, f)]
    if missing and not sys.stdin.isatty():
        raise UsageError(
            "missing " + " and ".join(f"--{m}" for m in missing)
            + ". Ask the human for the site NAME and its general PURPOSE; do not guess them."
        )
    if not args.name:
        args.name = prompt("Site name")
    if not args.purpose:
        args.purpose = prompt("What is the general purpose of the site? (one or two sentences)")
    return bool(missing)


def make_context(args):
    name = clean_line(args.name, "--name", 64)
    slug, package = derive_names(name)
    purpose = clean_line(args.purpose, "--purpose", 500)
    site_name = clean_line(args.site_name or default_site_name(name), "--site-name", 80)
    if args.license not in LICENSES:
        raise UsageError(f"unsupported --license {args.license!r}; choose from {', '.join(LICENSES)}")
    author = clean_line(args.author or git_config("user.name") or f"The {site_name} contributors", "--author", 80)
    contact = "GitHub private vulnerability reporting for this repository (or the maintainers listed in it)"
    variables = {
        "SITE_NAME": site_name, "PURPOSE": purpose, "PROJECT_PACKAGE": package, "LICENSE_SPDX": args.license,
        "YEAR": str(date.today().year), "COPYRIGHT_HOLDER": author, "MAINTAINER_CONTACT": contact,
    }
    return {
        "name": name, "slug": slug, "package": package, "purpose": purpose, "site_name": site_name,
        "license": args.license, "author": author, "vars": variables,
        "install": not args.no_venv, "opskit": not args.no_opskit,
    }


def check_target(parent, slug):
    parent = Path(parent).expanduser()
    if not parent.is_dir():
        raise UsageError(f"--parent-dir {str(parent)!r} is not an existing directory")
    parent = parent.resolve()
    target = parent / slug
    if target.parent != parent:  # defence in depth; derive_names already rules this out
        raise UsageError("derived directory escapes --parent-dir")
    if target.exists() or target.is_symlink():
        if not target.is_dir() or target.is_symlink() or any(target.iterdir()):
            raise UsageError(f"{target} already exists and is not an empty directory; refusing to touch it")
    return target


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        prompted = resolve_inputs(args)
        ctx = make_context(args)
        target = check_target(args.parent_dir, ctx["slug"])
        for needed in (DEFAULT_SITE, FOSS, VISUAL_CHECK):
            if not needed.exists():
                raise UsageError(f"skill assets are incomplete: {needed} is missing")
        plan = build_plan(ctx)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_STEP_FAILED

    print_plan(plan, target, ctx)
    if args.dry_run:
        print("Dry run: nothing was created.")
        return EXIT_OK
    if prompted and not args.yes:
        try:
            answer = prompt("Create this project? [y/N]").lower()
        except UsageError:
            answer = ""
        if answer not in ("y", "yes"):
            print("Aborted; nothing was created.")
            return EXIT_USAGE

    try:
        target.mkdir(exist_ok=True)
        print(f"== writing {len(plan.items)} files")
        write_plan(plan, target)
        password = build_project(ctx, target)
    except (StepError, OSError) as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        print(f"The partially built project was left at {target}. Fix the cause and re-run into a new "
              f"directory (this script never overwrites).", file=sys.stderr)
        return EXIT_STEP_FAILED

    port = free_port()
    py = "venv/bin/python" if ctx["install"] else "python"
    print()
    print(f"Created {ctx['site_name']!r} at {target}")
    if password:
        print(f"  Admin login:  admin / {password}")
        print("  This password is shown ONCE and is not stored anywhere: save it now (or reset it with "
              "`manage.py changepassword admin`).")
    else:
        print("  No venv/database was built (--no-venv). Follow README.md 'Quick start' to install and seed.")
    print("Next steps:")
    print(f"  cd {target}")
    print("  bin/verify.sh                      # check, migrations, tests, seed idempotency, Playwright screenshots")
    print(f"  DJANGO_DEBUG=1 DJANGO_SECRET_KEY=dev {py} manage.py runserver {port}")
    print()
    print("IMPORTANT: run bin/verify.sh and LOOK at verify-shots/*.png before telling anyone the site works.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
