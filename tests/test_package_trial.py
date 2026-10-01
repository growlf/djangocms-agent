"""Offline tests for bin/package-trial.py (no network, no venv). A live trial runs only with PACKAGE_TRIAL_LIVE=1."""
import importlib.util
import io
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "package-trial.py"
spec = importlib.util.spec_from_file_location("package_trial", SCRIPT)
pt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pt)


def cli(*args, **kw):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=120, **kw)


@pytest.mark.parametrize("spec_", ["djangocms-markdown", "djangocms-blog==2.0.10", "A.b_c-1==1.0.0rc1"])
def test_package_spec_accepts(spec_):
    assert pt.PKG_RE.match(spec_)


@pytest.mark.parametrize("spec_", ["--index-url=http://evil", "-r x", "pkg; rm -rf /", "pkg @ http://x/y.zip",
                                   "../x", "pkg>=1", "", "a b"])
def test_package_spec_rejects_option_injection(spec_):
    assert not pt.PKG_RE.match(spec_)


def test_default_app_and_module():
    assert pt.default_app("djangocms-blog==2.0.10") == "djangocms_blog"
    assert pt.default_app("Foo.Bar-baz") == "foo_bar_baz"
    assert pt.app_module("djangocms_blog.apps.BlogConfig") == "djangocms_blog.apps"
    assert pt.app_module("djangocms_blog") == "djangocms_blog"
    assert pt.app_module("djangocms_bootstrap5.contrib.bootstrap5_card") == "djangocms_bootstrap5.contrib.bootstrap5_card"


def test_settings_block_is_valid_python_and_appends():
    code = pt.settings_block(["a_app", "b.apps.BConfig"], "A_SETTING = 1")
    ns = {"INSTALLED_APPS": ["x"]}
    exec(compile(code, "settings", "exec"), ns)
    assert ns["INSTALLED_APPS"] == ["x", "a_app", "b.apps.BConfig"] and ns["A_SETTING"] == 1


def test_freeze_diff_flags_pinned_changes():
    before = pt.parse_freeze("Django==5.2.17\ndjango-cms==5.1.3\n-e git+x\n")
    after = pt.parse_freeze("Django==5.2.17\ndjango-cms==5.2.0\nnewpkg==1.0\n")
    d = pt.diff_freeze(before, after)
    assert d["added"] == {"newpkg": "1.0"} and d["changed"] == {"django-cms": ("5.1.3", "5.2.0")}
    assert not d["removed"]


def test_usage_errors_exit_2():
    assert cli("--index-url=x").returncode == 2  # unknown option -> argparse usage error
    p = cli("bad;name")
    assert p.returncode == 2 and "invalid package spec" in p.stderr and "Traceback" not in p.stderr
    p = cli("ok-name", "--app", "not valid")
    assert p.returncode == 2 and "--app" in p.stderr


def test_workdir_must_be_empty(tmp_path):
    (tmp_path / "f").write_text("x")
    p = cli("ok-name", "--workdir", str(tmp_path))
    assert p.returncode == 2 and "not empty" in p.stderr


def test_scaffold_step_builds_default_site_offline(tmp_path):
    args = pt.build_parser().parse_args(["demo-pkg", "--json"])
    t = pt.Trial(args, tmp_path)
    t.scaffold()
    assert (t.project / "manage.py").is_file() and (t.project / "requirements.txt").is_file()
    assert next(t.project.glob("*/settings.py")).is_file()
    assert t.steps[0]["status"] == "PASS"


def run_main(argv, **patches):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err), mock.patch.multiple(pt.Trial, **patches):
        return pt.main(argv), out.getvalue(), err.getvalue()


def test_failure_reports_step_tail_cleans_up_exit_1(tmp_path, monkeypatch):
    monkeypatch.setattr(pt.tempfile, "tempdir", str(tmp_path))
    def bad_install(self):
        raise pt.StepFailed("install candidate x", "ERROR: boom\nline2")
    code, out, _ = run_main(["demo-pkg"], scaffold=lambda self: None, install=bad_install)
    assert code == 1
    assert "Failing step: install candidate x" in out and "ERROR: boom" in out
    assert "TRIAL RESULT: FAIL (step: install candidate x)" in out
    assert "package-trial-" in out and not list(tmp_path.glob("package-trial-*")), "temp dir must be removed"


def test_pass_prints_limited_claim_and_keep_path(tmp_path, monkeypatch):
    monkeypatch.setattr(pt.tempfile, "tempdir", str(tmp_path))
    noop = lambda self: None
    code, out, _ = run_main(["demo-pkg", "--keep"], scaffold=noop, install=noop, configure=noop, verify=noop)
    assert code == 0 and "TRIAL RESULT: PASS" in out
    assert "does NOT mean the package renders" in out
    assert list(tmp_path.glob("package-trial-*")), "--keep must leave the dir"
    assert "Kept throwaway project" in out


def test_step_runner_reports_timeout_and_missing_binary(tmp_path):
    args = pt.build_parser().parse_args(["demo-pkg", "--json", "--step-timeout", "1"])
    t = pt.Trial(args, tmp_path)
    with pytest.raises(pt.StepFailed) as e:
        t.run("sleepy", [sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)
    assert "timed out" in e.value.output
    with pytest.raises(pt.StepFailed) as e:
        t.run("nobin", ["/nonexistent/binary"])
    assert "could not run" in e.value.output


@pytest.mark.skipif(os.environ.get("PACKAGE_TRIAL_LIVE") != "1", reason="set PACKAGE_TRIAL_LIVE=1 (network, ~30s)")
def test_live_trial_harmless_package():
    p = cli("djangocms-markdown", "--app", "djangocms_markdown")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "TRIAL RESULT: PASS" in p.stdout
