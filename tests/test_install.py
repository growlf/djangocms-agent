"""Unit tests for bin/install.py."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


INSTALLER = Path(__file__).resolve().parents[1] / "bin" / "install.py"


class TestInstall(unittest.TestCase):
    """Test install.py --project, --copy, --uninstall, --dry-run, and doctor."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="djangocms-test-")
        self.project_dir = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, *extra):
        """Run install.py and return CompletedProcess."""
        cmd = [sys.executable, str(INSTALLER)] + list(extra)
        return subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30,
            cwd=str(self.project_dir),
        )

    # ---- Basic install + assertions ----

    def test_copy_install_creates_all_targets(self):
        """--copy should create skills in .claude/skills, agents in .claude/agents,
        and generated agents in .opencode/agent."""
        result = self._run("--project", str(self.project_dir), "--copy", "--hosts", "claude,opencode")
        self.assertEqual(result.returncode, 0, result.stderr)

        # Skills exist
        skill_agent = self.project_dir / ".claude" / "skills" / "djangocms-agent"
        skill_reviewer = self.project_dir / ".claude" / "skills" / "djangocms-reviewer"
        self.assertTrue(skill_agent.exists(), ".claude/skills/djangocms-agent not found")
        self.assertTrue(skill_reviewer.exists(), ".claude/skills/djangocms-reviewer not found")

        # Claude agents exist
        agent_agent = self.project_dir / ".claude" / "agents" / "djangocms-agent.md"
        agent_reviewer = self.project_dir / ".claude" / "agents" / "djangocms-reviewer.md"
        self.assertTrue(agent_agent.exists(), ".claude/agents/djangocms-agent.md not found")
        self.assertTrue(agent_reviewer.exists(), ".claude/agents/djangocms-reviewer.md not found")

        # OpenCode agents exist
        oc_agent = self.project_dir / ".opencode" / "agent" / "djangocms-agent.md"
        oc_reviewer = self.project_dir / ".opencode" / "agent" / "djangocms-reviewer.md"
        self.assertTrue(oc_agent.exists(), ".opencode/agent/djangocms-agent.md not found")
        self.assertTrue(oc_reviewer.exists(), ".opencode/agent/djangocms-reviewer.md not found")

        # Lockfile exists
        lock = self.project_dir / ".djangocms-agent.lock"
        self.assertTrue(lock.exists())
        lock_data = json.loads(lock.read_text())
        self.assertIn("version", lock_data)
        self.assertIn("git_sha", lock_data)
        self.assertIn("files", lock_data)

    def test_opencode_agent_has_mode_subagent_no_name(self):
        """OpenCode agent must have mode: subagent and no name: in frontmatter."""
        result = self._run("--project", str(self.project_dir), "--copy", "--hosts", "claude,opencode")
        self.assertEqual(result.returncode, 0, result.stderr)

        oc_agent = self.project_dir / ".opencode" / "agent" / "djangocms-agent.md"
        content = oc_agent.read_text()

        self.assertIn("mode: subagent", content, "OpenCode agent missing mode: subagent")
        # Check no standalone name: in frontmatter
        lines = content.split("\n")
        for line in lines[:10]:  # Check first 10 lines (frontmatter area)
            self.assertFalse(
                line.strip().startswith("name:"),
                f"OpenCode agent has name: in frontmatter: {line}",
            )

    def test_opencode_skills_dir_not_created(self):
        """.opencode/skills should NOT be created by the installer."""
        result = self._run("--project", str(self.project_dir), "--copy", "--hosts", "claude,opencode")
        self.assertEqual(result.returncode, 0, result.stderr)

        oc_skills = self.project_dir / ".opencode" / "skills"
        self.assertFalse(oc_skills.exists(), ".opencode/skills was created (should not be)")

    # ---- Uninstall ----

    def test_uninstall_removes_files_and_lockfile(self):
        """--uninstall should remove all installed files and the lockfile."""
        # First install
        result = self._run("--project", str(self.project_dir), "--copy", "--hosts", "claude,opencode")
        self.assertEqual(result.returncode, 0, result.stderr)

        # Then uninstall
        result = self._run("--project", str(self.project_dir), "--uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)

        # Check files removed
        self.assertFalse(
            (self.project_dir / ".claude" / "skills" / "djangocms-agent").exists(),
            "Skill dir still exists after uninstall",
        )
        self.assertFalse(
            (self.project_dir / ".djangocms-agent.lock").exists(),
            "Lockfile still exists after uninstall",
        )

    # ---- Dry run ----

    def test_dry_run_prints_actions_no_changes(self):
        """--dry-run should print actions and change nothing."""
        result = self._run("--project", str(self.project_dir), "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DRY RUN", result.stdout)

        # Nothing should have been created
        self.assertFalse(
            (self.project_dir / ".claude").exists(),
            ".claude was created during dry run",
        )

    # ---- Doctor ----

    def test_doctor_ok(self):
        """doctor should print OK when installed and up-to-date."""
        result = self._run("--project", str(self.project_dir), "--copy", "--hosts", "claude,opencode")
        self.assertEqual(result.returncode, 0, result.stderr)

        result = self._run("--project", str(self.project_dir), "doctor")
        self.assertIn("OK", result.stdout, f"doctor output: {result.stdout}")
        self.assertEqual(result.returncode, 0)

    def test_doctor_no_lockfile(self):
        """doctor should exit 2 when no lockfile exists."""
        result = self._run("--project", str(self.project_dir), "doctor")
        self.assertEqual(result.returncode, 2)

    def test_doctor_behind(self):
        """doctor should exit 1 and print BEHIND when lockfile sha differs."""
        # Install first
        result = self._run("--project", str(self.project_dir), "--copy", "--hosts", "claude,opencode")
        self.assertEqual(result.returncode, 0, result.stderr)

        # Tamper with the lockfile to make it appear behind
        import json as _json
        lock_path = self.project_dir / ".djangocms-agent.lock"
        data = _json.loads(lock_path.read_text())
        data["git_sha"] = "abcdef0"  # fake old sha
        lock_path.write_text(_json.dumps(data))

        result = self._run("--project", str(self.project_dir), "doctor")
        self.assertEqual(result.returncode, 1)
        self.assertIn("BEHIND", result.stdout)

    def test_dry_run_no_claude_dir(self):
        """--dry-run should not create .claude directory."""
        result = self._run("--project", str(self.project_dir), "--dry-run")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(
            (self.project_dir / ".claude").exists(),
            ".claude created during dry run",
        )


if __name__ == "__main__":
    unittest.main()
