"""Tests for bin/install.py. Every test uses its own temp dir (and a temp HOME for --global)."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / "bin" / "install.py"
NAMES = ["djangocms-agent", "djangocms-reviewer"]


def load_module():
    spec = importlib.util.spec_from_file_location("install_mod", INSTALLER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def frontmatter(text):
    lines = text.split("\n")
    assert lines[0] == "---", "file must start with ---"
    end = lines.index("---", 1)
    return lines[1:end], "\n".join(lines[end + 1:])


class Base(unittest.TestCase):
    def setUp(self):
        self.proj = Path(tempfile.mkdtemp(prefix="dcms-proj-"))
        self.home = Path(tempfile.mkdtemp(prefix="dcms-home-"))
        self.addCleanup(shutil.rmtree, self.proj, True)
        self.addCleanup(shutil.rmtree, self.home, True)

    def run_cli(self, *args, project=True):
        cmd = [sys.executable, str(INSTALLER), *args]
        if project and "--global" not in args:
            cmd += ["--project", str(self.proj)]
        env = dict(os.environ, HOME=str(self.home))
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)

    def tree(self, root):
        return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() or p.is_symlink())


class TestInstall(Base):
    def test_copy_install_layout(self):
        r = self.run_cli("--copy")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for n in NAMES:
            self.assertTrue((self.proj / ".claude/skills" / n / "SKILL.md").is_file())
            self.assertTrue((self.proj / ".claude/agents" / f"{n}.md").is_file())
            self.assertTrue((self.proj / ".opencode/agent" / f"{n}.md").is_file())
        self.assertFalse((self.proj / ".opencode/skills").exists(), "skills must be installed once")
        self.assertFalse((self.proj / ".agents").exists())
        lock = json.loads((self.proj / ".djangocms-agent.lock").read_text())
        self.assertEqual(len(lock["files"]), 6)
        self.assertEqual(lock["mode"], "copy")

    def test_link_install_uses_relative_symlinks_into_source(self):
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for n in NAMES:
            link = self.proj / ".claude/skills" / n
            self.assertTrue(link.is_symlink())
            self.assertFalse(os.path.isabs(os.readlink(link)))
            self.assertEqual(link.resolve(), (REPO / "skills" / n).resolve())

    def test_opencode_agent_is_valid_and_correct(self):
        self.run_cli("--copy")
        for n in NAMES:
            text = (self.proj / ".opencode/agent" / f"{n}.md").read_text()
            front, body = frontmatter(text)
            keys = [l.split(":", 1)[0] for l in front]
            self.assertEqual(keys, ["description", "mode", "tags"], front)
            self.assertNotIn("name", keys)
            self.assertIn("mode: subagent", front)
            src_front, _ = frontmatter((REPO / "agents" / f"{n}.md").read_text())
            src_desc = next(l for l in src_front if l.startswith("description:"))
            self.assertIn(src_desc, front, "description must be copied verbatim")
            self.assertNotIn("True", text)
            self.assertNotIn("opencode-permission", text)
            self.assertIn("You are the DjangoCMS", body)

    def test_claude_agent_is_copied_unchanged(self):
        self.run_cli("--copy")
        for n in NAMES:
            self.assertEqual((self.proj / ".claude/agents" / f"{n}.md").read_text(),
                             (REPO / "agents" / f"{n}.md").read_text())

    def test_permission_comment_becomes_permission_map(self):
        mod = load_module()
        src = ("---\nname: x\ndescription: 'd: e'\n---\n"
               '<!-- opencode-permission: {"relay-shell_*": "deny", "mikromcp_*": true} -->\nBody\n')
        out = mod.generate_opencode_agent(src)
        front, body = frontmatter(out)
        self.assertIn('  "relay-shell_*": deny', front)
        self.assertIn('  "mikromcp_*": allow', front)
        self.assertEqual(body.strip(), "Body")

    def test_multiline_description_is_rejected(self):
        mod = load_module()
        with self.assertRaises(mod.InstallError):
            mod.generate_opencode_agent("---\nname: x\ndescription: >-\n  a\n---\nB\n")

    def test_reinstall_is_idempotent_and_uninstall_is_complete(self):
        for flag in ("--copy", "--link"):
            with self.subTest(flag=flag):
                self.assertEqual(self.run_cli(flag).returncode, 0)
                r = self.run_cli(flag)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                lock = json.loads((self.proj / ".djangocms-agent.lock").read_text())
                self.assertEqual(len(lock["files"]), 6)
                self.assertEqual(self.run_cli("--uninstall").returncode, 0)
                self.assertEqual(self.tree(self.proj), [])
                self.assertFalse((self.proj / ".claude").exists(), "empty dirs must be pruned")

    def test_conflict_changes_nothing(self):
        foreign = self.proj / ".opencode/agent/djangocms-agent.md"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("mine")
        r = self.run_cli("--copy")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.tree(self.proj), [".opencode/agent/djangocms-agent.md"])
        self.assertEqual(foreign.read_text(), "mine")

    def test_uninstall_leaves_foreign_files(self):
        self.run_cli("--copy")
        mine = self.proj / ".claude/agents/mine.md"
        mine.write_text("keep")
        skill_extra = self.proj / ".claude/skills/other-skill/SKILL.md"
        skill_extra.parent.mkdir(parents=True)
        skill_extra.write_text("keep")
        self.assertEqual(self.run_cli("--uninstall").returncode, 0)
        self.assertTrue(mine.exists())
        self.assertTrue(skill_extra.exists())

    def test_tampered_lockfile_cannot_delete_unmanaged_names(self):
        self.run_cli("--copy")
        victim = self.proj / "precious.txt"
        victim.write_text("x")
        lockp = self.proj / ".djangocms-agent.lock"
        lock = json.loads(lockp.read_text())
        lock["files"].append("precious.txt")
        lockp.write_text(json.dumps(lock))
        self.run_cli("--uninstall")
        self.assertTrue(victim.exists())

    def test_dry_run_changes_nothing_and_lists_actions(self):
        r = self.run_cli("--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.tree(self.proj), [])
        self.assertEqual(r.stdout.count("[dry-run] would"), 6)

    def test_dry_run_uninstall_changes_nothing(self):
        self.run_cli("--copy")
        before = self.tree(self.proj)
        r = self.run_cli("--uninstall", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.tree(self.proj), before)

    def test_hosts_opencode_only(self):
        self.assertEqual(self.run_cli("--copy", "--hosts", "opencode").returncode, 0)
        self.assertFalse((self.proj / ".claude/agents").exists())
        self.assertTrue((self.proj / ".claude/skills/djangocms-agent").exists())
        self.assertTrue((self.proj / ".opencode/agent/djangocms-agent.md").exists())

    def test_hosts_crush_only_installs_skills_and_says_so(self):
        r = self.run_cli("--copy", "--hosts", "crush")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Crush reads .claude/skills", r.stdout)
        self.assertFalse((self.proj / ".claude/agents").exists())
        self.assertFalse((self.proj / ".opencode").exists())

    def test_unknown_host_is_an_error(self):
        self.assertEqual(self.run_cli("--hosts", "vim").returncode, 2)

    def test_global_installs_under_home_not_the_repo(self):
        r = self.run_cli("--copy", "--global")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for n in NAMES:
            self.assertTrue((self.home / ".claude/skills" / n).is_dir())
            self.assertTrue((self.home / ".claude/agents" / f"{n}.md").is_file())
            self.assertTrue((self.home / ".config/opencode/agent" / f"{n}.md").is_file())
        self.assertTrue((self.home / ".claude/.djangocms-agent.lock").is_file())
        self.assertFalse((REPO / ".djangocms-agent.lock").exists(), "must not write into the source repo")
        self.assertEqual(self.run_cli("--global", "--uninstall").returncode, 0)
        self.assertEqual([p for p in self.tree(self.home)], [])


class TestDoctor(Base):
    def test_no_lockfile_exits_2(self):
        self.assertEqual(self.run_cli("doctor").returncode, 2)

    def test_ok_exits_0(self):
        self.run_cli("--copy")
        r = self.run_cli("doctor")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("OK", r.stdout)

    def test_behind_exits_1(self):
        self.run_cli("--copy")
        lockp = self.proj / ".djangocms-agent.lock"
        lock = json.loads(lockp.read_text())
        lock["version"], lock["git_sha"] = "0.0.1", "deadbee"
        lockp.write_text(json.dumps(lock))
        r = self.run_cli("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertIn("BEHIND: installed 0.0.1/deadbee", r.stdout)

    def test_missing_file_exits_1(self):
        self.run_cli("--copy")
        (self.proj / ".claude/agents/djangocms-agent.md").unlink()
        r = self.run_cli("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISSING: .claude/agents/djangocms-agent.md", r.stdout)


class TestAssetsSymlink(Base):
    """The default-site template must be reachable from an installed skill (link and copy modes)."""

    MARKER = "assets/default-site/starter/seeding.py"

    def test_source_symlink_points_at_repo_assets(self):
        link = REPO / "skills/djangocms-agent/assets"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), "../../assets")
        self.assertTrue((link / "default-site/templates/base.html").is_file())

    def _check(self, flag):
        self.assertEqual(self.run_cli(flag).returncode, 0)
        skill = self.proj / ".claude/skills/djangocms-agent"
        for rel in ("assets/default-site/templates/base.html", "assets/default-site/static/vendor/bootstrap/LICENSE",
                    "assets/default-site/settings_fragment.py", self.MARKER):
            self.assertTrue((skill / rel).is_file(), rel)
        r = self.run_cli("doctor")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("OK", r.stdout)
        return skill

    def test_link_install_resolves_assets_and_uninstalls(self):
        self._check("--link")
        self.assertEqual(self.run_cli("--uninstall").returncode, 0)
        self.assertEqual(self.tree(self.proj), [])
        self.assertTrue((REPO / "assets/default-site/templates/base.html").is_file(), "uninstall must not touch the source")

    def test_copy_install_resolves_assets_and_uninstalls(self):
        skill = self._check("--copy")
        self.assertFalse(skill.joinpath("assets").is_symlink(), "copy mode materialises the files")
        self.assertEqual(self.run_cli("--uninstall").returncode, 0)
        self.assertEqual(self.tree(self.proj), [])

    def test_default_site_has_no_testsite_leftovers(self):
        bad = ("testlog", "Test Site", "task #139", "OutcomeCallout", "testsite")
        root = REPO / "assets/default-site"
        for path in root.rglob("*"):
            if path.is_file() and "vendor" not in path.parts and path.suffix in {".py", ".html", ".css", ".js", ".md", ".txt"}:
                text = path.read_text()
                for word in bad:
                    self.assertNotIn(word, text, f"{path.relative_to(root)} mentions {word!r}")

    def test_python_assets_compile(self):
        for path in (REPO / "assets/default-site").rglob("*.py"):
            compile(path.read_text(), str(path), "exec")


if __name__ == "__main__":
    unittest.main()
