"""Offline tests for bin/djangopackages.py (fixtures under tests/fixtures; no network).

One optional live smoke test runs only when DJANGOPACKAGES_LIVE=1.
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "djangopackages.py"
FIX = Path(__file__).parent / "fixtures"

spec = importlib.util.spec_from_file_location("djangopackages", SCRIPT)
dp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dp)


def fx(name):
    return json.loads((FIX / name).read_text())


PYPI = {"djangocms-blog": "pypi_djangocms_blog.json", "django-cms": "pypi_django-cms.json",
        "django-headless-cms": "pypi_django-headless-cms.json"}
PKG_BY_ID = {}
for _s in ("django-cms", "djangocms-blog", "django-headless-cms", "django-cms-search"):
    _d = fx(f"package_{_s}.json")
    PKG_BY_ID[str(_d["id"])] = _d


def fake_get_json(url, timeout, use_cache=True, allow_404=False):
    """Route every URL the CLI can ask for to a recorded fixture."""
    if "/search/" in url:
        return fx("search_django_cms_blog.json")
    if "/grids/djangocms-plugins/" in url:
        return fx("grid_djangocms_plugins.json")
    if "/grids/" in url and url.rstrip("/").split("/")[-1].isdigit():
        return {"slug": "django-cms", "title": "Django-CMS", "packages": []}
    if "/grids/?" in url:
        return {"count": 2, "results": [
            {"slug": "seo", "title": "SEO", "description": "", "packages": ["a"] * 20},
            {"slug": "forms", "title": "Forms", "description": "form libs", "packages": []}]}
    if "/packages/" in url:
        key = url.rstrip("/").split("/")[-1]
        if key in PKG_BY_ID:
            return PKG_BY_ID[key]
        for d in PKG_BY_ID.values():
            if d["slug"] == key:
                return d
        raise dp.Fail(f"not found (HTTP 404): {url}")
    if "pypi" in url:
        name = url.rstrip("/").split("/")[-2]
        if name in PYPI:
            return fx(PYPI[name])
        if allow_404:
            return None
    raise AssertionError(f"unexpected URL {url}")


def run_cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(dp, "get_json", fake_get_json), redirect_stdout(out), redirect_stderr(err):
        code = dp.main(list(args))
    return code, out.getvalue(), err.getvalue()


# ---- parsing + enrichment ------------------------------------------------------------------

def test_package_from_detail_fields():
    r = dp.package_from_detail(fx("package_djangocms-blog.json"))
    assert r["slug"] == "djangocms-blog"
    assert r["pypi_name"] == "djangocms-blog"
    assert r["repo_url"] == "https://github.com/nephila/djangocms-blog"
    assert r["category"] == "App"
    assert r["repo_watchers"] > 100 and r["commits_last_52_weeks"] > 0
    assert r["last_commit"].startswith("20")


def test_package_without_slug_is_data_error():
    with pytest.raises(dp.Fail) as e:
        dp.package_from_detail({"title": "x"})
    assert e.value.code == dp.EXIT_DATA


def test_summarise_pypi_fixture():
    s = dp.summarise_pypi(fx("pypi_djangocms_blog.json"))
    assert s["version"] == "2.0.10"
    assert s["released"] == "2026-07-06"
    assert s["django_classifiers"] == ["3.2", "4.1", "4.2"]
    assert s["cms_requirement"] == "<4.0,>=3.9"
    assert s["requires_python"] == ">=3.7"
    assert s["license"] == "BSD"
    assert "github.com/nephila/djangocms-blog" in " ".join(s["urls"])


def test_summarise_pypi_malformed():
    with pytest.raises(dp.Fail):
        dp.summarise_pypi({"nope": 1})


@pytest.mark.parametrize("url,name", [
    ("http://pypi.python.org/pypi/django-cms", "django-cms"),
    ("https://pypi.org/project/djangocms-blog/", "djangocms-blog"),
    ("", None), (None, None), ("https://example.com/x", None)])
def test_pypi_name_from_url(url, name):
    assert dp.pypi_name_from_url(url) == name


def test_repo_match():
    p = dp.summarise_pypi(fx("pypi_djangocms_blog.json"))
    assert dp.repo_matches("https://github.com/nephila/djangocms-blog.git", p) == "yes"
    assert dp.repo_matches("https://github.com/evil/djangocms-blog", p) == "no"
    assert dp.repo_matches(None, p) == "unknown"
    assert dp.repo_matches("https://github.com/a/b", None) == "unknown"


# ---- specifier + compat heuristic ----------------------------------------------------------

@pytest.mark.parametrize("spec_,ver,expected", [
    (">=3.10", (3, 12), True), (">=3.7,<3.12", (3, 12), False), ("<4.0,>=3.9", (5, 1), False),
    (">=4.1.1", (5, 1), True), ("~=3.8", (3, 12), True), ("==3.12.*", (3, 12), True),
    ("!=3.12.*", (3, 12), False), ("", (3, 12), True), (None, (3, 12), True), ("garbage", (3, 12), None)])
def test_spec_allows(spec_, ver, expected):
    assert dp.spec_allows(spec_, ver) is expected


def pypi(**kw):
    base = {"yanked": False, "requires_python": ">=3.10", "cms_requirement": None, "django_classifiers": [],
            "python_classifiers": [], "released": "2026-06-01"}
    base.update(kw)
    return base


TODAY = date(2026, 10, 1)


def test_compat_likely_when_52_declared_and_recent():
    v = dp.compat_verdict(pypi(django_classifiers=["4.2", "5.2"]), today=TODAY)
    assert v["verdict"] == "likely"


def test_compat_unlikely_when_cms_requirement_excludes_51():
    v = dp.compat_verdict(pypi(django_classifiers=["5.2"], cms_requirement="<4.0,>=3.9"), today=TODAY)
    assert v["verdict"] == "unlikely" and "excludes 5.1" in " ".join(v["reasons"])


def test_compat_unlikely_when_python_excluded():
    v = dp.compat_verdict(pypi(django_classifiers=["5.2"], requires_python=">=3.8,<3.12"), today=TODAY)
    assert v["verdict"] == "unlikely"


def test_compat_unknown_without_classifiers_but_recent():
    assert dp.compat_verdict(pypi(), today=TODAY)["verdict"] == "unknown"


def test_compat_unknown_when_only_50_declared():
    assert dp.compat_verdict(pypi(django_classifiers=["4.2", "5.0"]), today=TODAY)["verdict"] == "unknown"


def test_compat_unlikely_for_old_django_only():
    assert dp.compat_verdict(pypi(django_classifiers=["3.2"]), today=TODAY)["verdict"] == "unlikely"


def test_compat_unlikely_when_stale_and_undeclared():
    v = dp.compat_verdict(pypi(released="2019-01-01"), today=TODAY)
    assert v["verdict"] == "unlikely"


def test_compat_stale_but_declared_is_not_likely():
    v = dp.compat_verdict(pypi(released="2022-01-01", django_classifiers=["5.2"]), today=TODAY)
    assert v["verdict"] == "unknown"


def test_compat_missing_pypi_and_yanked():
    assert dp.compat_verdict(None, "x")["verdict"] == "unknown"
    assert dp.compat_verdict(pypi(yanked=True), today=TODAY)["verdict"] == "unlikely"


@pytest.mark.parametrize("name", ["djangocms-social", "djangocms_text_ckeditor", "DjangoCMS-Form"])
def test_compat_known_bad_names_from_plugins_matrix(name):
    v = dp.compat_verdict(pypi(django_classifiers=["5.2"]), name, today=TODAY)
    assert v["verdict"] == "unlikely" and "known problem" in v["reasons"][0]


# ---- HTTP error handling (urlopen mocked) --------------------------------------------------

def http_error(code, headers=None):
    return urllib.error.HTTPError("http://x", code, "msg", headers or {}, None)


def test_get_json_timeout_is_clear_fail():
    with mock.patch("urllib.request.urlopen", side_effect=TimeoutError()):
        with pytest.raises(dp.Fail) as e:
            dp.get_json("http://x/", 1.5, use_cache=False)
    assert "timed out after 1.5s" in str(e.value) and e.value.code == dp.EXIT_NETWORK


def test_get_json_urlerror_timeout_and_dns():
    with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError(TimeoutError())):
        with pytest.raises(dp.Fail, match="timed out"):
            dp.get_json("http://x/", 1, use_cache=False)
    with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Name or service not known")):
        with pytest.raises(dp.Fail, match="network error"):
            dp.get_json("http://x/", 1, use_cache=False)


def test_get_json_429_retries_once_then_fails():
    calls = []
    def boom(*a, **k):
        calls.append(1)
        raise http_error(429, {"Retry-After": "1"})
    with mock.patch("urllib.request.urlopen", side_effect=boom), mock.patch.object(dp.time, "sleep") as sl:
        with pytest.raises(dp.Fail) as e:
            dp.get_json("http://x/", 1, use_cache=False)
    assert len(calls) == 2 and sl.called
    assert "rate limited" in str(e.value) and e.value.code == dp.EXIT_NETWORK


def test_get_json_429_long_wait_not_slept():
    with mock.patch("urllib.request.urlopen", side_effect=http_error(429, {"Retry-After": "600"})), \
            mock.patch.object(dp.time, "sleep") as sl:
        with pytest.raises(dp.Fail, match="600s"):
            dp.get_json("http://x/", 1, use_cache=False)
    assert not sl.called


def test_get_json_404_and_500():
    with mock.patch("urllib.request.urlopen", side_effect=http_error(404)):
        assert dp.get_json("http://x/", 1, use_cache=False, allow_404=True) is None
        with pytest.raises(dp.Fail, match="404"):
            dp.get_json("http://x/", 1, use_cache=False)
    with mock.patch("urllib.request.urlopen", side_effect=http_error(503)):
        with pytest.raises(dp.Fail, match="HTTP 503"):
            dp.get_json("http://x/", 1, use_cache=False)


def test_get_json_malformed_body_is_data_error():
    resp = mock.MagicMock()
    resp.__enter__.return_value.read.return_value = b"<html>not json</html>"
    with mock.patch("urllib.request.urlopen", return_value=resp):
        with pytest.raises(dp.Fail) as e:
            dp.get_json("http://x/", 1, use_cache=False)
    assert e.value.code == dp.EXIT_DATA and "not valid JSON" in str(e.value)


def test_user_agent_names_the_skill():
    seen = {}
    resp = mock.MagicMock()
    resp.__enter__.return_value.read.return_value = b"{}"
    def capture(req, timeout):
        seen["ua"] = req.get_header("User-agent")
        return resp
    with mock.patch("urllib.request.urlopen", side_effect=capture):
        dp.get_json("http://x/", 1, use_cache=False)
    assert "djangocms-agent" in seen["ua"]


def test_cache_roundtrip_and_no_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    resp = mock.MagicMock()
    resp.__enter__.return_value.read.return_value = b'{"a": 1}'
    with mock.patch("urllib.request.urlopen", return_value=resp) as uo:
        assert dp.get_json("http://x/a", 1) == {"a": 1}
        assert dp.get_json("http://x/a", 1) == {"a": 1}
        assert uo.call_count == 1
        dp.get_json("http://x/a", 1, use_cache=False)
        assert uo.call_count == 2
    assert list((tmp_path / "djangocms-agent" / "djangopackages").glob("*.json"))


# ---- commands via CLI entry point ----------------------------------------------------------

def test_search_table_and_verdicts():
    code, out, err = run_cli("search", "django cms blog")
    assert code == 0, err
    assert "djangocms-blog" in out and "django-cms" in out
    blog = [l for l in out.splitlines() if l.startswith("djangocms-blog")][0]
    assert blog.rstrip().endswith("unlikely")
    assert "compat heuristic" in out and "Related grids: django-cms" in out
    assert "Related grids: django-cms  " in out


def test_search_json_is_valid_and_structured():
    code, out, _ = run_cli("search", "django cms blog", "--json", "--limit", "2")
    data = json.loads(out)
    assert code == 0 and data["kind"] == "search" and len(data["packages"]) == 2
    assert {"slug", "pypi", "compat", "repo_match", "repo_watchers"} <= set(data["packages"][0])


def test_search_no_pypi_skips_enrichment():
    code, out, _ = run_cli("search", "x", "--no-pypi", "--json")
    data = json.loads(out)
    assert code == 0 and all(p["pypi"] is None for p in data["packages"])
    assert data["packages"][0]["compat"]["verdict"] == "unknown"


def test_search_empty_results_exit_zero_with_message():
    with mock.patch.object(dp, "get_json", return_value=[]), redirect_stdout(io.StringIO()) as out:
        code = dp.main(["search", "zzzqqq"])
    assert code == 0 and "No packages found" in out.getvalue()


def test_search_unexpected_payload_exit_2():
    err = io.StringIO()
    with mock.patch.object(dp, "get_json", return_value={"detail": "x"}), redirect_stderr(err):
        code = dp.main(["search", "x"])
    assert code == 2 and "unexpected search payload" in err.getvalue()


def test_search_blank_query_exit_2():
    code, _, err = run_cli("search", "   ")
    assert code == 2 and "empty query" in err


def test_grid_ranks_by_watchers():
    code, out, err = run_cli("grid", "djangocms-plugins", "--limit", "3")
    assert code == 0, err
    assert "Grid: Django CMS Plugins" in out
    assert out.index("django-cms ") < out.index("djangocms-blog ")  # 10k watchers before ~500


def test_grid_missing_exit_1():
    def nf(url, *a, **k):
        raise dp.Fail("not found (HTTP 404): " + url)
    err = io.StringIO()
    with mock.patch.object(dp, "get_json", nf), redirect_stderr(err):
        code = dp.main(["grid", "nope"])
    assert code == 1 and "404" in err.getvalue() and "Traceback" not in err.getvalue()


def test_grids_filter():
    code, out, _ = run_cli("grids", "seo")
    assert code == 0 and "seo" in out and "forms" not in out.split("\n", 1)[1]


def test_show_package_with_grid_names():
    code, out, _ = run_cli("show", "djangocms-blog", "--json")
    data = json.loads(out)["packages"][0]
    assert code == 0 and data["slug"] == "djangocms-blog"
    assert data["pypi"]["version"] == "2.0.10" and data["compat"]["verdict"] == "unlikely"
    assert data["grids"]


def test_show_unknown_package_exit_1():
    code, _, err = run_cli("show", "does-not-exist")
    assert code == 1 and "404" in err


def test_pypi_lookup_failure_degrades_to_unknown():
    def flaky(url, timeout, use_cache=True, allow_404=False):
        if "pypi" in url:
            raise dp.Fail("timed out after 1s: " + url)
        return fake_get_json(url, timeout, use_cache, allow_404)
    out = io.StringIO()
    with mock.patch.object(dp, "get_json", flaky), redirect_stdout(out):
        code = dp.main(["show", "djangocms-blog"])
    assert code == 0 and "PyPI lookup failed" in out.getvalue()


# ---- subprocess: no traceback when the network is unreachable -----------------------------

def test_cli_network_down_exit_1_no_traceback(tmp_path):
    env = {**os.environ, "DJANGOPACKAGES_API": "http://127.0.0.1:9", "XDG_CACHE_HOME": str(tmp_path)}
    p = subprocess.run([sys.executable, str(SCRIPT), "search", "blog", "--timeout", "2"],
                       capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 1
    assert "Traceback" not in p.stderr and p.stderr.startswith("error:")


def test_cli_usage_error_exit_2():
    p = subprocess.run([sys.executable, str(SCRIPT), "bogus"], capture_output=True, text=True, timeout=30)
    assert p.returncode == 2 and "Traceback" not in p.stderr
    p = subprocess.run([sys.executable, str(SCRIPT), "search", "x", "--limit", "0"], capture_output=True,
                       text=True, timeout=30)
    assert p.returncode == 2


# ---- optional live smoke -------------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("DJANGOPACKAGES_LIVE") != "1", reason="set DJANGOPACKAGES_LIVE=1 for the live smoke test")
def test_live_smoke(tmp_path):
    env = {**os.environ, "XDG_CACHE_HOME": str(tmp_path)}
    p = subprocess.run([sys.executable, str(SCRIPT), "search", "django cms blog", "--limit", "3", "--json"],
                       capture_output=True, text=True, env=env, timeout=120)
    assert p.returncode == 0, p.stderr
    assert any(x["slug"] == "djangocms-blog" for x in json.loads(p.stdout)["packages"])
