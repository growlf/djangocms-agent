#!/usr/bin/env python3
"""Idempotent installer for the djangocms-agent skills and agent definitions.

Usage:
    bin/install.py [--global | --project DIR] [--copy | --link]
                   [--hosts claude,opencode,crush] [--uninstall] [--dry-run]
    bin/install.py doctor [--global | --project DIR]

Where things go (every host reads skills from .claude/skills, so each skill is
installed exactly once there):
    skills   <base>/.claude/skills/<name>            Claude Code, OpenCode, Crush
    agents   <base>/.claude/agents/<name>.md         Claude Code   (host "claude")
    agents   <base>/.opencode/agent/<name>.md        OpenCode      (host "opencode", generated)
Global mode: base = $HOME, OpenCode agents in ~/.config/opencode/agent/.

A lockfile (.djangocms-agent.lock) records what was installed so re-installs,
uninstalls and `doctor` only ever touch files this installer created.
Exit codes: 0 ok, 1 conflict / behind / missing files, 2 error or no lockfile.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_NAMES = ["djangocms-agent", "djangocms-reviewer"]
AGENT_NAMES = ["djangocms-agent", "djangocms-reviewer"]
LOCK_FILE = ".djangocms-agent.lock"
HOSTS = ("claude", "opencode", "crush")
OPENCODE_TAGS = "[django, django-cms, cms]"
# Only these basenames may ever be removed by --uninstall.
MANAGED_NAMES = set(SKILL_NAMES) | {f"{n}.md" for n in AGENT_NAMES}


class InstallError(Exception):
    pass


# --------------------------------------------------------------------------- source info

def source_root():
    return Path(__file__).resolve().parents[1]


def catalog_version(root):
    data = json.loads((root / "catalog.json").read_text())
    for plugin in data.get("plugins", []):
        if plugin.get("id") == "djangocms-agent":
            return plugin.get("version", "unknown")
    return "unknown"


def git_sha(root):
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# --------------------------------------------------------------------------- agent generation

def split_frontmatter(text):
    """Return (frontmatter_lines, body) for a '---' delimited file."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise InstallError("agent file has no frontmatter")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], "\n".join(lines[i + 1:])
    raise InstallError("agent file frontmatter is not closed")


def generate_opencode_agent(text):
    """Claude-format agent file -> OpenCode-format file.

    Drops `name:`; keeps `description:` verbatim; adds `mode: subagent` and tags;
    turns a non-empty `<!-- opencode-permission: {...} -->` comment into a
    `permission:` map. The comment itself is not carried over.
    """
    front, body = split_frontmatter(text)
    description = None
    for line in front:
        m = re.match(r"^description:\s*(.*)$", line)
        if m:
            description = m.group(1).strip()
    if not description or description in (">", ">-", "|", "|-"):
        raise InstallError("agent description must be a single-line value")

    permission = {}
    m = re.search(r"<!--\s*opencode-permission:\s*(\{.*?\})\s*-->", body)
    if m:
        try:
            permission = json.loads(m.group(1))
        except json.JSONDecodeError as exc:
            raise InstallError(f"bad opencode-permission JSON: {exc}")
        body = body.replace(m.group(0), "", 1)

    out = ["---", f"description: {description}", "mode: subagent", f"tags: {OPENCODE_TAGS}"]
    if permission:
        out.append("permission:")
        for key, value in permission.items():
            if isinstance(value, bool):
                value = "allow" if value else "deny"
            out.append(f'  "{key}": {value}')
    out.append("---")
    return "\n".join(out) + "\n" + body.lstrip("\n")


# --------------------------------------------------------------------------- planning

class Plan:
    def __init__(self, lock_dir):
        self.lock_dir = lock_dir
        self.actions = []        # (kind, dest, payload)

    def add(self, kind, dest, payload=None):
        self.actions.append((kind, dest, payload))

    def dests(self):
        return [d for _, d, _ in self.actions]


def layout(args):
    """Return (claude_base, opencode_agent_dir, lock_dir)."""
    if args.global_mode:
        home = Path.home()
        return home / ".claude", home / ".config" / "opencode" / "agent", home / ".claude"
    root = Path(args.project).resolve()
    return root / ".claude", root / ".opencode" / "agent", root


def build_plan(args, src):
    claude_base, opencode_agents, lock_dir = layout(args)
    plan = Plan(lock_dir)
    mode = "copy" if args.copy else "link"
    for name in SKILL_NAMES:
        skill_src = src / "skills" / name
        if not skill_src.is_dir():
            raise InstallError(f"missing source skill: {skill_src}")
        plan.add(f"skill-{mode}", claude_base / "skills" / name, skill_src)
    if "claude" in args.hosts:
        for name in AGENT_NAMES:
            plan.add("file", claude_base / "agents" / f"{name}.md",
                     (src / "agents" / f"{name}.md").read_text())
    if "opencode" in args.hosts:
        for name in AGENT_NAMES:
            plan.add("file", opencode_agents / f"{name}.md",
                     generate_opencode_agent((src / "agents" / f"{name}.md").read_text()))
    return plan


# --------------------------------------------------------------------------- lockfile

def read_lock(lock_dir):
    path = lock_dir / LOCK_FILE
    return json.loads(path.read_text()) if path.exists() else None


def owned_paths(lock_dir, lock):
    return {(lock_dir / rel) for rel in (lock or {}).get("files", [])}


def rel(path, lock_dir):
    return os.path.relpath(str(path), str(lock_dir))


def remove_path(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def prune_empty(dirs):
    for d in sorted(set(dirs), key=lambda p: len(p.parts), reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass


# --------------------------------------------------------------------------- commands

def cmd_install(args, src):
    plan = build_plan(args, src)
    lock_dir = plan.lock_dir
    lock = read_lock(lock_dir)
    owned = owned_paths(lock_dir, lock)

    conflicts = [d for d in plan.dests() if (d.exists() or d.is_symlink()) and d not in owned]
    if conflicts:
        for c in conflicts:
            print(f"SKIP (exists and not managed by this installer): {c}")
        print("Nothing was changed.")
        return 1

    prefix = "[dry-run] would " if args.dry_run else ""
    for kind, dest, payload in plan.actions:
        verb = "link" if kind == "skill-link" else "copy" if kind == "skill-copy" else "write"
        print(f"{prefix}{verb} {dest}")
        if args.dry_run:
            continue
        if dest.exists() or dest.is_symlink():
            remove_path(dest)            # ours (checked above): replace cleanly
        dest.parent.mkdir(parents=True, exist_ok=True)
        if kind == "skill-link":
            dest.symlink_to(os.path.relpath(str(payload), str(dest.parent)))
        elif kind == "skill-copy":
            shutil.copytree(payload, dest, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            dest.write_text(payload)

    if "crush" in args.hosts:
        print("Crush reads .claude/skills; nothing extra to install.")
    if args.dry_run:
        return 0

    files = sorted({rel(d, lock_dir) for d in plan.dests()} | set((lock or {}).get("files", [])))
    (lock_dir / LOCK_FILE).write_text(json.dumps({
        "version": catalog_version(src),
        "git_sha": git_sha(src),
        "mode": "copy" if args.copy else "link",
        "files": files,
    }, indent=2) + "\n")
    print(f"Installed {len(plan.actions)} items under {lock_dir}")
    return 0


def cmd_uninstall(args, src):
    _, _, lock_dir = layout(args)
    lock = read_lock(lock_dir)
    if lock is None:
        print(f"No lockfile found at {lock_dir / LOCK_FILE}")
        return 2
    prefix = "[dry-run] would " if args.dry_run else ""
    parents = []
    for relpath in lock.get("files", []):
        path = lock_dir / relpath
        if path.name not in MANAGED_NAMES:
            print(f"SKIP (not a name this installer manages): {path}")
            continue
        if path.exists() or path.is_symlink():
            print(f"{prefix}remove {path}")
            if not args.dry_run:
                remove_path(path)
        parents.append(path.parent)
    if not args.dry_run:
        (lock_dir / LOCK_FILE).unlink()
        extra = [p.parent for p in parents] + [p.parent.parent for p in parents]
        prune_empty(parents + extra)
    print(f"{prefix}Uninstalled from {lock_dir}")
    return 0


def cmd_doctor(args, src):
    _, _, lock_dir = layout(args)
    lock = read_lock(lock_dir)
    if lock is None:
        print(f"No lockfile found at {lock_dir / LOCK_FILE}")
        return 2
    issues = 0
    inst = (lock.get("version", "unknown"), lock.get("git_sha", "unknown"))
    now = (catalog_version(src), git_sha(src))
    if inst != now:
        print(f"BEHIND: installed {inst[0]}/{inst[1]}, source {now[0]}/{now[1]}")
        issues += 1
    else:
        print("OK")
    for relpath in lock.get("files", []):
        path = lock_dir / relpath
        if not (path.exists() or path.is_symlink()):
            print(f"MISSING: {relpath}")
            issues += 1
    return 1 if issues else 0


# --------------------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(description="Install/uninstall djangocms-agent skills and agents.")
    p.add_argument("command", nargs="?", choices=["doctor"], help="'doctor' checks an existing install")
    p.add_argument("--global", dest="global_mode", action="store_true", help="install under $HOME")
    p.add_argument("--project", default=".", help="project directory (default: .)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--copy", action="store_true", help="copy skills instead of symlinking")
    mode.add_argument("--link", action="store_true", help="symlink skills (default)")
    p.add_argument("--hosts", default="claude,opencode", help="comma list of: claude,opencode,crush")
    p.add_argument("--uninstall", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="show actions, change nothing")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    bad = [h for h in args.hosts if h not in HOSTS]
    if bad:
        print(f"unknown host(s): {', '.join(bad)} (choose from {', '.join(HOSTS)})", file=sys.stderr)
        return 2
    src = source_root()
    try:
        if args.command == "doctor":
            return cmd_doctor(args, src)
        if args.uninstall:
            return cmd_uninstall(args, src)
        return cmd_install(args, src)
    except (InstallError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
