#!/usr/bin/env python3
"""Trial a PyPI package in a THROWAWAY copy of the default site. Never touches a real project.

Usage:
    bin/package-trial.py <pypi-name[==version]> [--app DOTTED ...] [--settings 'PYTHON CODE' | --settings-file F]
                         [--requirement REQ ...] [--keep] [--workdir DIR] [--step-timeout S]
                         [--pip-arg ARG ...] [--allow-sdist] [--json]

Only run this when the user has asked to try or install a package. It:
  1. scaffolds the default site into a fresh temp directory (bin/new-site.py --no-venv, nothing else),
  2. creates a venv and installs the site's pinned requirements.txt, then the candidate (wheels only unless
     --allow-sdist, so no arbitrary build script runs; plus any --requirement extras),
  3. records what the candidate pulled in and whether it changed any pinned version, runs `pip check`,
  4. appends the apps (--app, default: the PyPI name with '-' -> '_') and your --settings code to settings.py,
  5. imports the app, then runs `manage.py check`, `migrate --noinput`, and `makemigrations --check --dry-run`
     for the candidate's own app labels (the bootstrap5 apps in the base site always show drift, so a project-wide
     check would be noise) and lists the CMS plugins/apphooks it registered.
It prints PASS/FAIL/SKIP per step, the exact failing step with an output tail, and removes the temp
directory unless --keep (then it prints the path).

PASS MEANS ONLY: it installed, imported, passed `check` and `migrate`, and added no migration drift. It does NOT
mean the package renders correctly in the CMS, works with the default theme, or is safe. After a PASS: install it
in the real site (references/django-packages.md), then run that site's bin/verify.sh and look at the screenshots.

Exit codes: 0 PASS; 1 FAIL (a step failed; named in the output); 2 usage error or the skill assets are missing.
Needs network (PyPI) and Python 3.12+. Standard library only. Uses ports: none.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

EXIT_PASS, EXIT_FAIL, EXIT_USAGE = 0, 1, 2
ROOT = Path(__file__).resolve().parents[1]
NEW_SITE = ROOT / "bin" / "new-site.py"
DISCLAIMER = ("PASS means only: installed, imported, `check` and `migrate` worked and no migration drift for the "
              "package's own apps. It does NOT mean the package renders or works in the CMS, fits the theme, or is "
              "safe. Next: install it in the real site, run its bin/verify.sh and look at the screenshots.")

PKG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(==[A-Za-z0-9.!+_*-]+)?$")
APP_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


class StepFailed(Exception):
    def __init__(self, step: str, output: str):
        super().__init__(step)
        self.step, self.output = step, output


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def default_app(pkg: str) -> str:
    return re.split(r"==", pkg)[0].replace("-", "_").replace(".", "_").lower()


def app_module(entry: str) -> str:
    """'pkg.apps.PkgConfig' -> 'pkg.apps'; 'pkg' -> 'pkg' (an AppConfig class segment starts uppercase)."""
    parts = entry.split(".")
    if len(parts) > 1 and parts[-1][:1].isupper():
        parts = parts[:-1]
    return ".".join(parts)


def settings_block(apps: list[str], extra: str) -> str:
    lines = ["", "# --- package-trial (throwaway; appended by bin/package-trial.py) ---"]
    for a in apps:
        lines.append(f"INSTALLED_APPS += [{a!r}]")
    if extra.strip():
        lines += [extra.rstrip(), ""]
    return "\n".join(lines) + "\n"


def parse_freeze(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)$", line.strip())
        if m:
            out[norm(m.group(1))] = m.group(2)
    return out


def diff_freeze(before: dict[str, str], after: dict[str, str]) -> dict:
    return {
        "added": {k: v for k, v in after.items() if k not in before},
        "changed": {k: (before[k], after[k]) for k in after if k in before and before[k] != after[k]},
        "removed": {k: v for k, v in before.items() if k not in after},
    }


# Run inside the trial venv after django.setup(): resolves the candidate's app labels and what it registered.
INSPECT = r"""
import json, sys
import django
django.setup()
from django.apps import apps
from django.db.migrations.loader import MigrationLoader
wanted = json.loads(sys.argv[1])
labels, rows = [], []
loader = MigrationLoader(None, ignore_no_migrations=True)
for c in apps.get_app_configs():
    cls = type(c).__module__ + "." + type(c).__name__
    if c.name in wanted or cls in wanted:
        labels.append(c.label)
        rows.append({"label": c.label, "name": c.name, "models": len(list(c.get_models())),
                     "has_migrations": c.label in loader.migrated_apps})
plugins, hooks = [], []
try:
    from cms.plugin_pool import plugin_pool
    plugin_pool.discover_plugins()
    for p in plugin_pool.get_all_plugins():
        mod = p.__module__
        if any(mod == w or mod.startswith(w + ".") or mod.split(".")[0] == w.split(".")[0] for w in wanted):
            plugins.append(p.__name__)
except Exception as e:
    plugins.append("(could not list plugins: %s)" % e)
try:
    from cms.apphook_pool import apphook_pool
    apphook_pool.discover_apps()
    for name, app in apphook_pool.apps.items():
        mod = type(app).__module__ if not isinstance(app, type) else app.__module__
        if any(mod.split(".")[0] == w.split(".")[0] for w in wanted):
            hooks.append(name)
except Exception as e:
    hooks.append("(could not list apphooks: %s)" % e)
print("INSPECT " + json.dumps({"labels": labels, "apps": rows, "plugins": plugins, "apphooks": hooks}))
"""


class Trial:
    def __init__(self, args, base: Path):
        self.a = args
        self.base = base
        self.steps: list[dict] = []
        self.project: Path | None = None
        self.vpy: str | None = None
        self.info: dict = {}

    # -- runner
    def run(self, name: str, cmd: list, *, cwd=None, env=None, timeout=None, tolerate=False) -> str:
        t0 = time.time()
        timeout = timeout or self.a.step_timeout
        try:
            proc = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=timeout)
            out, rc = proc.stdout or "", proc.returncode
        except subprocess.TimeoutExpired as e:
            out, rc = (e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")) + \
                f"\n[timed out after {timeout:g}s]", 124
        except OSError as e:
            out, rc = f"[could not run command: {e}]", 127
        rec = {"step": name, "status": "PASS" if rc == 0 else "FAIL", "seconds": round(time.time() - t0, 1)}
        if rc != 0:
            rec["output_tail"] = "\n".join(out.splitlines()[-30:])
        self.steps.append(rec)
        self._echo(rec)
        if rc != 0 and not tolerate:
            raise StepFailed(name, rec["output_tail"])
        return out

    def note(self, name: str, status: str, detail: str = "") -> None:
        rec = {"step": name, "status": status, "seconds": 0.0, "detail": detail}
        self.steps.append(rec)
        self._echo(rec)

    def _echo(self, rec: dict) -> None:
        if not self.a.json:
            extra = f"  {rec['detail']}" if rec.get("detail") else ""
            print(f"[{rec['status']:<4}] {rec['step']} ({rec['seconds']}s){extra}", flush=True)

    # -- steps
    def env(self) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME")}
        env.update(DJANGO_DEBUG="1", DJANGO_SECRET_KEY="package-trial-throwaway", DJANGO_DEBUG_TOOLBAR="0",
                   PIP_DISABLE_PIP_VERSION_CHECK="1", PYTHONDONTWRITEBYTECODE="1")
        return env

    def scaffold(self) -> None:
        self.run("scaffold throwaway site", [sys.executable, NEW_SITE, "--name", "trial site",
                                             "--purpose", f"throwaway trial of {self.a.package}",
                                             "--parent-dir", self.base, "--no-venv", "--no-opskit", "--yes"],
                 env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull},
                 timeout=120)
        self.project = self.base / "trial-site"
        if not (self.project / "manage.py").is_file():
            raise StepFailed("scaffold throwaway site", f"manage.py not found in {self.project}")

    def install(self) -> None:
        env = self.env()
        self.run("create venv", [sys.executable, "-m", "venv", self.project / "venv"], cwd=self.project, env=env)
        self.vpy = str(self.project / "venv" / "bin" / "python")
        pip = [self.vpy, "-m", "pip", "install", "--quiet", *self.a.pip_arg]
        self.run("install pinned site requirements", [*pip, "-r", "requirements.txt"], cwd=self.project, env=env)
        before_txt = self.run("freeze (before candidate)", [self.vpy, "-m", "pip", "freeze"], cwd=self.project, env=env)
        base_check = self.run("pip check (baseline)", [self.vpy, "-m", "pip", "check"], cwd=self.project, env=env,
                              tolerate=True)
        wheels = [] if self.a.allow_sdist else ["--only-binary", ":all:"]
        self.run(f"install candidate {self.a.package}",
                 [*pip, *wheels, self.a.package, *self.a.requirement], cwd=self.project, env=env)
        after_txt = self.run("freeze (after candidate)", [self.vpy, "-m", "pip", "freeze"], cwd=self.project, env=env)
        d = diff_freeze(parse_freeze(before_txt), parse_freeze(after_txt))
        self.info["pulled_in"] = d
        pinned_changed = d["changed"] or d["removed"]
        self.note("what the candidate pulled in", "FAIL" if pinned_changed else "PASS",
                  f"{len(d['added'])} new package(s): {', '.join(f'{k}=={v}' for k, v in sorted(d['added'].items())) or 'none'}"
                  + (f"; CHANGED/REMOVED PINNED: { {**d['changed'], **d['removed']} }" if pinned_changed else ""))
        if pinned_changed:
            raise StepFailed("candidate changed pinned site requirements",
                             f"changed={d['changed']} removed={d['removed']}\n"
                             "Installing this package would move versions the default site is verified with.")
        meta = self.run("candidate metadata", [self.vpy, "-m", "pip", "show", re.split(r"==", self.a.package)[0]],
                        cwd=self.project, env=env, tolerate=True)
        fields = dict(re.findall(r"^(Name|Version|License|License-Expression|Home-page|Requires): ?(.*)$", meta, re.M))
        self.info["installed"] = fields
        after_check = self.run("pip check (after candidate)", [self.vpy, "-m", "pip", "check"], cwd=self.project,
                               env=env, tolerate=True)
        new_problems = sorted(set(after_check.splitlines()) - set(base_check.splitlines()))
        new_problems = [p for p in new_problems if p.strip() and "No broken requirements" not in p]
        if new_problems:
            self.steps[-1]["status"] = "FAIL"
            raise StepFailed("pip check (new dependency conflicts)", "\n".join(new_problems))
        self.steps[-1]["status"] = "PASS"

    def configure(self) -> None:
        apps = self.a.app or [default_app(self.a.package)]
        extra = self.a.settings or ""
        if self.a.settings_file:
            extra += "\n" + Path(self.a.settings_file).read_text()
        settings = next(self.project.glob("*/settings.py"))
        with settings.open("a") as fh:
            fh.write(settings_block(apps, extra))
        self.apps = apps
        self.note("add to INSTALLED_APPS (appended last)", "PASS", ", ".join(apps))

    def verify(self) -> None:
        env, vpy, mods = self.env(), self.vpy, [app_module(a) for a in self.apps]
        for m in mods:
            self.run(f"import {m}", [vpy, "-c", f"import importlib; importlib.import_module({m!r})"],
                     cwd=self.project, env=env)
        self.run("manage.py check", [vpy, "manage.py", "check"], cwd=self.project, env=env)
        self.run("manage.py migrate --noinput", [vpy, "manage.py", "migrate", "--noinput"], cwd=self.project, env=env)
        out = self.run("inspect candidate apps", [vpy, "-c", INSPECT, json.dumps(self.apps + mods)],
                       cwd=self.project, env={**env, "DJANGO_SETTINGS_MODULE": f"{self.project.name.replace('-', '_')}.settings"})
        m = re.search(r"^INSPECT (.*)$", out, re.M)
        insp = json.loads(m.group(1)) if m else {"labels": [], "apps": [], "plugins": [], "apphooks": []}
        self.info["inspect"] = insp
        if insp["labels"]:
            self.run(f"makemigrations --check --dry-run {' '.join(insp['labels'])}",
                     [vpy, "manage.py", "makemigrations", "--check", "--dry-run", *insp["labels"]],
                     cwd=self.project, env=env)
        else:
            self.note("makemigrations --check", "SKIP",
                      "no Django app label matched --app (the package may be a plain library); pass the right --app")


def report(t: Trial, failure: StepFailed | None, keep_path: Path | None) -> int:
    verdict = "FAIL" if failure else "PASS"
    if t.a.json:
        print(json.dumps({"package": t.a.package, "apps": getattr(t, "apps", None), "result": verdict,
                          "failed_step": failure.step if failure else None, "steps": t.steps, "info": t.info,
                          "kept": str(keep_path) if keep_path else None, "note": DISCLAIMER}, indent=2))
        return EXIT_FAIL if failure else EXIT_PASS
    print()
    if failure:
        print(f"Failing step: {failure.step}")
        print("Output tail:\n" + "\n".join("    " + line for line in failure.output.splitlines()[-25:]))
    inst, insp = t.info.get("installed", {}), t.info.get("inspect")
    if inst:
        print(f"Installed: {inst.get('Name')} {inst.get('Version')}  license: "
              f"{inst.get('License-Expression') or inst.get('License') or '?'}")
    if insp:
        print("App labels: " + (", ".join(insp["labels"]) or "none")
              + "; ships migrations: " + (", ".join(f"{r['label']}={'yes' if r['has_migrations'] else 'no'}" for r in insp["apps"]) or "n/a")
              + f"; CMS plugins: {', '.join(insp['plugins']) or 'none'}; apphooks: {', '.join(insp['apphooks']) or 'none'}")
    if keep_path:
        print(f"Kept throwaway project: {keep_path} (delete it when done)")
    print(f"TRIAL RESULT: {verdict}" + (f" (step: {failure.step})" if failure else ""))
    print(DISCLAIMER if not failure else "The real site was not touched. Do not add this package to it as-is; read the failing step first.")
    return EXIT_FAIL if failure else EXIT_PASS


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="package-trial.py", description=__doc__.split("\n\n")[0])
    p.add_argument("package", help="PyPI name, optionally pinned: djangocms-blog==2.0.10")
    p.add_argument("--app", action="append", default=[], metavar="DOTTED",
                   help="INSTALLED_APPS entry (repeatable; default: PyPI name with - replaced by _)")
    p.add_argument("--settings", help="Python code appended to settings.py (e.g. a package setting)")
    p.add_argument("--settings-file", help="file whose contents are appended to settings.py")
    p.add_argument("--requirement", action="append", default=[], help="extra pip requirement (repeatable)")
    p.add_argument("--keep", action="store_true", help="do not delete the temp project; print its path")
    p.add_argument("--workdir", help="use this (new or empty) directory instead of a temp dir")
    p.add_argument("--step-timeout", type=float, default=900.0, help="seconds per step (default 900)")
    p.add_argument("--pip-arg", action="append", default=[], help="extra argument for pip install (repeatable)")
    p.add_argument("--allow-sdist", action="store_true", help="allow source distributions (runs build scripts)")
    p.add_argument("--json", action="store_true", help="machine-readable report")
    return p


def validate(a) -> str | None:
    if not PKG_RE.match(a.package):
        return f"invalid package spec {a.package!r} (expected NAME or NAME==VERSION)"
    for app in a.app:
        if not APP_RE.match(app):
            return f"invalid --app {app!r} (expected a dotted Python path)"
    for r in a.requirement:
        if not PKG_RE.match(r):
            return f"invalid --requirement {r!r} (expected NAME or NAME==VERSION)"
    if a.settings_file and not Path(a.settings_file).is_file():
        return f"--settings-file {a.settings_file!r} does not exist"
    if sys.version_info < (3, 12):
        return "Python 3.12+ is required"
    if not NEW_SITE.is_file() or not (ROOT / "assets" / "default-site").is_dir():
        return "skill assets are missing (bin/new-site.py, assets/default-site)"
    return None


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    err = validate(a)
    if err:
        print(f"error: {err}", file=sys.stderr)
        return EXIT_USAGE
    if a.workdir:
        base = Path(a.workdir).resolve()
        if base.exists() and any(base.iterdir()):
            print(f"error: --workdir {base} exists and is not empty", file=sys.stderr)
            return EXIT_USAGE
        base.mkdir(parents=True, exist_ok=True)
    else:
        base = Path(tempfile.mkdtemp(prefix="package-trial-"))
    t, failure = Trial(a, base), None
    if not a.json:
        print(f"Trial of {a.package} in a throwaway site at {base}\n")
    try:
        t.scaffold()
        t.install()
        t.configure()
        t.verify()
    except StepFailed as e:
        failure = e
    except KeyboardInterrupt:
        failure = StepFailed("interrupted", "interrupted by user")
    keep = base if (a.keep or a.workdir) else None
    code = report(t, failure, keep)
    if not keep:
        shutil.rmtree(base, ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
