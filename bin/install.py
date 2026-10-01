#!/usr/bin/env python3
"""Idempotent multi-host installer for the djangocms-agent skill/agent definitions.

Usage:
    bin/install.py [--global | --project DIR] [--copy | --link]
                   [--hosts claude,opencode,crush] [--uninstall] [--dry-run]
    bin/install.py doctor [--project DIR | --global]

Defaults: --project ., --link, --hosts claude,opencode
"""
import argparse
import glob as glob_mod
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKILL_NAMES = ["djangocms-agent", "djangocms-reviewer"]
AGENT_NAMES = ["djangocms-agent", "djangocms-reviewer"]
LOCK_FILE = ".djangocms-agent.lock"

# Global paths
GLOBAL_CLAUDE = Path.home() / ".claude"

# OpenCode reads from ~/.config/opencode
OPENCODE_GLOBAL = Path.home() / ".config" / "opencode"


# ---------------------------------------------------------------------------
# Catalog reader
# ---------------------------------------------------------------------------

def _load_catalog(root):
    """Return parsed catalog.json from source root."""
    catalog_path = root / "catalog.json"
    with open(catalog_path) as f:
        return json.load(f)


def _git_sha(root):
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# OpenCode agent generation
# ---------------------------------------------------------------------------

def _generate_opencode_agent(claude_agent_path):
    """Generate OpenCode-format agent file from Claude-format source.

    - Drop `name:` from frontmatter
    - Keep `description:`
    - Add `mode: subagent`, `tags: [django, django-cms, cms]`
    - Add `permission:` map only if opencode-permission comment holds non-empty JSON
    """
    with open(claude_agent_path) as f:
        lines = f.readlines()

    result = []
    in_frontmatter = False
    found_description = False
    found_permission = None

    for line in lines:
        stripped = line.rstrip("\n")

        # Handle frontmatter boundaries
        if stripped == "---":
            if not in_frontmatter:
                in_frontmatter = True
                result.append("---")
                continue
            else:
                in_frontmatter = False
                result.append("---")
                # Now inject the OpenCode-specific frontmatter
                result.append("mode: subagent")
                result.append("tags: [django, django-cms, cms]")

                if found_description:
                    result.append(f"description: '{found_description}'")
                else:
                    result.append("description: 'DjangoCMS specialist agent.'")

                # Add permission if non-empty
                if found_permission:
                    m = re.search(r"opencode-permission:\s*(\{.*\})", found_permission)
                    if m:
                        try:
                            perm_obj = json.loads(m.group(1))
                            if perm_obj:
                                result.append("permission:")
                                for key in perm_obj:
                                    result.append(f"  {key}: true")
                        except json.JSONDecodeError:
                            pass
                result.append("")
                continue

        if in_frontmatter:
            # Skip name: line, keep description:
            if stripped.startswith("name:"):
                continue
            if stripped.startswith("description:"):
                # Extract description value
                m = re.match(r"^\s*description:\s*['\"](.*?)['\"]\s*$", stripped)
                if m:
                    found_description = m.group(1)
                else:
                    m2 = re.match(r"^\s*description:\s*>-\s*$", stripped)
                    if m2:
                        # Multi-line description — collect until blank or next key
                        desc_lines = []
                        continue
                    found_description = stripped.split(":", 1)[1].strip().strip("'\"")
                found_description = True if found_description else False
                continue
            if "opencode-permission:" in stripped:
                found_permission = stripped
            continue

        # After frontmatter: keep the rest as-is
        result.append(line)

    return "".join(result)


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------

def _relative_symlink(target_dir, source_rel, dest_name):
    """Create a relative symlink from target_dir/dest_name to source_rel."""
    dest = target_dir / dest_name
    if dest.exists() or dest.is_symlink():
        # Check if it's our own symlink
        if dest.is_symlink():
            try:
                existing_target = os.readlink(str(dest))
                if existing_target == str(source_rel):
                    return dest  # Already correct
            except OSError:
                pass
    target_dir.mkdir(parents=True, exist_ok=True)
    dest.symlink_to(source_rel)
    return dest


def _write_file(dest, content):
    """Write content to dest, creating parent dirs."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    return dest


def _read_lockfile(target_root):
    """Read the lockfile if it exists."""
    lock_path = target_root / LOCK_FILE
    if lock_path.exists():
        with open(lock_path) as f:
            return json.load(f)
    return None


def _write_lockfile(target_root, version, git_sha, mode, files):
    """Write the lockfile."""
    lock_path = target_root / LOCK_FILE
    data = {
        "version": version,
        "git_sha": git_sha,
        "mode": mode,
        "files": files,
    }
    lock_path.write_text(json.dumps(data, indent=2) + "\n")


def _remove_lockfile_files(target_root):
    """Remove files listed in lockfile, then the lockfile itself.
    Returns 0 if lockfile existed and was removed, 2 if not found."""
    lock_path = target_root / LOCK_FILE
    if not lock_path.exists():
        return 2
    lock_data = json.loads(lock_path.read_text())
    files_created = lock_data.get("files", [])
    for fpath in files_created:
        full = target_root / fpath
        if full.is_dir() and not full.is_symlink():
            shutil.rmtree(str(full), ignore_errors=True)
        elif full.exists() or full.is_symlink():
            try:
                full.unlink()
            except OSError:
                pass
    try:
        lock_path.unlink()
    except OSError:
        pass
    return 0


# ---------------------------------------------------------------------------
# Install logic
# ---------------------------------------------------------------------------

def _install(args, source_root, is_global=False):
    """Core install/uninstall logic."""
    if args.uninstall:
        return _do_uninstall(source_root, args.project)

    version_info = _load_catalog(source_root)
    version = version_info.get("plugins", [{}])[0].get("version", "unknown")
    git_sha = _git_sha(source_root)
    mode = "copy" if args.copy else "link"

    target_root = source_root if is_global else Path(args.project).resolve()
    conflicts = []
    created_files = []

    # --- Skills (Claude format, installed once in .claude/skills) ---
    skill_source = source_root / "skills"
    skill_target = target_root / ".claude" / "skills"

    if skill_target.exists() and skill_target.is_symlink():
        pass  # Will handle below
    skill_target.mkdir(parents=True, exist_ok=True)

    for skill_name in SKILL_NAMES:
        skill_src = skill_source / skill_name
        if not skill_src.is_dir():
            continue

        if mode == "link":
            # Create relative symlink
            rel_target = os.path.relpath(str(skill_src), str(skill_target.parent))
            dest = skill_target / skill_name
            if dest.exists() or dest.is_symlink():
                if dest.is_symlink():
                    try:
                        existing = os.readlink(str(dest))
                        if existing == rel_target:
                            continue  # Already correct
                    except OSError:
                        pass
                else:
                    # Existing real dir — conflict
                    conflicts.append(f"{dest}")
                    continue
            else:
                dest.symlink_to(rel_target)
                created_files.append(f".claude/skills/{skill_name}")
        else:
            # Copy
            dest = skill_target / skill_name
            if dest.exists():
                if dest.is_dir() and not dest.is_symlink():
                    conflicts.append(f"{dest}")
                    continue
                dest.unlink()
            # Copy entire skill dir
            import shutil
            dest.mkdir(parents=True, exist_ok=True)
            for item in skill_src.iterdir():
                if item.is_dir():
                    shutil.copytree(item, dest / item.name)
                else:
                    shutil.copy2(item, dest)
            created_files.append(f".claude/skills/{skill_name}")

    # --- Claude agents ---
    agents_target = target_root / ".claude" / "agents"
    agents_target.mkdir(parents=True, exist_ok=True)
    agents_source = source_root / "agents"

    for agent_name in AGENT_NAMES:
        agent_src = agents_source / f"{agent_name}.md"
        if not agent_src.exists():
            continue
        agent_dest = agents_target / f"{agent_name}.md"

        if agent_dest.exists() and not agent_dest.is_symlink():
            # Check if it's ours
            lock = _read_lockfile(target_root)
            if lock and agent_dest.name in [f.split("/")[-1] for f in lock.get("files", [])]:
                pass  # Our file, will overwrite
            else:
                conflicts.append(str(agent_dest))
                continue

        content = agent_src.read_text()
        agent_dest.write_text(content)
        created_files.append(f".claude/agents/{agent_name}.md")

    # --- OpenCode agents (generated) ---
    if "opencode" in args.hosts:
        opencode_agents_target = target_root / ".opencode" / "agent"
        opencode_agents_target.mkdir(parents=True, exist_ok=True)

        for agent_name in AGENT_NAMES:
            agent_src = agents_source / f"{agent_name}.md"
            if not agent_src.exists():
                continue
            agent_dest = opencode_agents_target / f"{agent_name}.md"

            if agent_dest.exists() and not agent_dest.is_symlink():
                lock = _read_lockfile(target_root)
                if lock and agent_dest.name in [f.split("/")[-1] for f in lock.get("files", [])]:
                    pass
                else:
                    conflicts.append(str(agent_dest))
                    continue

            # Generate OpenCode format
            opencode_content = _generate_opencode_agent(agent_src)
            agent_dest.write_text(opencode_content)
            created_files.append(f".opencode/agent/{agent_name}.md")

    # Report conflicts
    if conflicts:
        for c in conflicts:
            print(f"SKIP (existing, not managed): {c}")
        return 1

    # Write lockfile
    _write_lockfile(target_root, version, git_sha, mode, created_files)

    print(f"Installed {len(created_files)} files to {target_root}")
    for f in created_files:
        print(f"  + {f}")
    return 0


def _do_uninstall(source_root, project_dir):
    """Uninstall from the target directory."""
    target_root = Path(project_dir).resolve() if project_dir else source_root
    files_removed = _remove_lockfile_files(target_root)
    if files_removed == 2:
        print(f"No lockfile found at {target_root}")
        return 2
    print(f"Uninstalled from {target_root}")
    return 0


# ---------------------------------------------------------------------------
# Doctor command
# ---------------------------------------------------------------------------

def _doctor(args, source_root, is_global=False):
    """Doctor subcommand: verify lockfile state."""
    target_root = source_root if is_global else Path(args.project).resolve()
    lock_path = target_root / LOCK_FILE

    if not lock_path.exists():
        print(f"No lockfile found at {target_root}")
        return 2

    lock_data = json.loads(lock_path.read_text())
    installed_version = lock_data.get("version", "unknown")
    installed_sha = lock_data.get("git_sha", "unknown")

    source_sha = _git_sha(source_root)
    source_version = _load_catalog(source_root).get("plugins", [{}])[0].get("version", "unknown")

    issues = 0

    if installed_version != source_version or installed_sha != source_sha:
        print(f"BEHIND: installed {installed_version}/{installed_sha}, source {source_version}/{source_sha}")
        issues += 1
    else:
        print("OK")

    # Verify all files exist
    for fpath in lock_data.get("files", []):
        full = target_root / fpath
        if not full.exists() and not full.is_symlink():
            print(f"MISSING: {fpath}")
            issues += 1

    if issues > 0:
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        description="Install/uninstall djangocms-agent skills and agents.",
    )
    parser.add_argument("--global", dest="global_mode", action="store_true",
                        help="Install to global paths (~/.claude/)")
    parser.add_argument("--project", default=".",
                        help="Project directory (default: current dir)")
    parser.add_argument("--copy", action="store_true",
                        help="Copy files instead of creating symlinks")
    parser.add_argument("--link", action="store_true", default=True,
                        help="Create symlinks for skills (default)")
    parser.add_argument("--hosts", default="claude,opencode",
                        help="Comma-separated host list: claude,opencode,crush")
    parser.add_argument("--uninstall", action="store_true",
                        help="Remove previously installed files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print actions without making changes")
    return parser


def main():
    parser = build_parser()

    # Handle 'doctor' subcommand
    if "doctor" in sys.argv[1:]:
        doctor_parser = argparse.ArgumentParser()
        doctor_parser.add_argument("--global", dest="global_mode", action="store_true")
        doctor_parser.add_argument("--project", default=".",
                                    help="Project directory (default: current dir)")
        # Consume 'doctor' positional
        doctor_parser.add_argument("subcommand", nargs="?", default="doctor")
        args = doctor_parser.parse_args(sys.argv[1:])
        # Remove the subcommand from the namespace
        del args.subcommand

        source_root = Path(__file__).resolve().parents[1]
        return _doctor(args, source_root, is_global=args.global_mode)

    args = parser.parse_args()

    source_root = Path(__file__).resolve().parents[1]

    # Parse hosts
    hosts = [h.strip() for h in getattr(args, "hosts", "claude,opencode").split(",")]

    if "crush" in hosts and len(set(hosts) - {"crush"}) == 0:
        print("Crush reads .claude/skills; nothing extra to install.")
        return 0

    if args.dry_run:
        print(f"[DRY RUN] Would install to {args.project} (global={args.global_mode})")
        print(f"  Hosts: {hosts}")
        print(f"  Mode: {'copy' if args.copy else 'link'}")
        print(f"  Skills: {SKILL_NAMES}")
        print(f"  Agents: {AGENT_NAMES}")
        return 0

    return _install(args, source_root, is_global=args.global_mode)


if __name__ == "__main__":
    sys.exit(main())
