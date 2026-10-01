#!/usr/bin/env python3
"""Search Django Packages (djangopackages.org) and compare candidates for a django CMS site.

Usage:
    bin/djangopackages.py search <query>      [--limit N] [--json] [--no-pypi] [--timeout S] [--no-cache]
    bin/djangopackages.py grid   <grid-slug>  [--limit N] [--scan N] [--json] ...
    bin/djangopackages.py grids  [text]       list grids (categories of comparable packages), optionally filtered
    bin/djangopackages.py show   <package-slug> [--json] ...

What it does: queries the public, key-less Django Packages API v4 (verified 2026-10-01, see
references/django-packages.md), then enriches every package from the PyPI JSON API (latest version, release
date, requires_python, Django/Python classifiers, license, django-cms requirement, whether the PyPI project
links back to the repo) and prints a compact comparable table plus a COMPATIBILITY HEURISTIC for
Django 5.2 + Python 3.12+ (likely / unknown / unlikely). The heuristic reads metadata only. It never
installs or imports anything, and "likely" is NOT "works": the trial (bin/package-trial.py) and
bin/verify.sh decide that.

Exit codes: 0 success (an empty result set is success: it says so); 1 network or service failure (timeout,
DNS, HTTP 429/5xx, package or grid not found); 2 usage error or an unexpected/malformed API response.
Never prints a traceback for those cases.

Etiquette: sends a User-Agent naming this skill, caches successful responses for 6 hours under
$XDG_CACHE_HOME/djangocms-agent/djangopackages (--no-cache to bypass), retries a 429 once when the server
asks for a short wait. Python 3.12+, standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

EXIT_OK, EXIT_NETWORK, EXIT_DATA = 0, 1, 2

API = os.environ.get("DJANGOPACKAGES_API", "https://djangopackages.org/api/v4").rstrip("/")
PYPI = os.environ.get("DJANGOPACKAGES_PYPI", "https://pypi.org/pypi").rstrip("/")
USER_AGENT = "djangocms-agent-djangopackages/1.0 (+https://github.com/growlf/djangocms-agent)"
CACHE_TTL = 6 * 3600
TARGET_DJANGO = (5, 2)
TARGET_PYTHONS = ((3, 12), (3, 13), (3, 14))
TARGET_CMS = (5, 1)

# Findings recorded in references/plugins.md (verified on cms 5.1.3 / Django 5.2). Keyed by normalised PyPI name.
KNOWN = {
    "djangocms-form": "not on PyPI under this name (references/plugins.md)",
    "djangocms-social": "0.4a1 imports ugettext_lazy and crashes Django 5.2 (references/plugins.md)",
    "djangocms-text-ckeditor": "superseded by djangocms-text; keep it out of INSTALLED_APPS (references/plugins.md)",
    "djangocms-snippet": "unsuitable with djangocms-versioning (references/plugins.md)",
}


class Fail(Exception):
    """A reportable failure; `code` is the process exit code."""

    def __init__(self, message: str, code: int = EXIT_NETWORK):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- HTTP + cache

def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "djangocms-agent" / "djangopackages"


def _cache_path(url: str) -> Path:
    return cache_dir() / (hashlib.sha256(url.encode()).hexdigest() + ".json")


def cache_get(url: str):
    try:
        data = json.loads(_cache_path(url).read_text())
        if time.time() - data["at"] < CACHE_TTL:
            return data["body"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def cache_put(url: str, body) -> None:
    try:
        cache_dir().mkdir(parents=True, exist_ok=True)
        _cache_path(url).write_text(json.dumps({"at": time.time(), "url": url, "body": body}))
    except OSError:
        pass  # the cache is an optimisation only


def get_json(url: str, timeout: float, use_cache: bool = True, allow_404: bool = False):
    """GET `url` and return parsed JSON; None for a 404 when allow_404. Raises Fail with a clear message."""
    if use_cache:
        hit = cache_get(url)
        if hit is not None:
            return hit
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404 and allow_404:
                return None
            if e.code == 404:
                raise Fail(f"not found (HTTP 404): {url}") from None
            if e.code == 429:
                wait = _retry_after(e)
                if attempt == 1 and wait is not None and wait <= 10:
                    time.sleep(wait)
                    continue
                raise Fail(f"rate limited (HTTP 429) by {urllib.parse.urlparse(url).netloc}"
                           f"{f'; server asks to wait {wait:.0f}s' if wait else ''}. Retry later, "
                           "or use cached results / the website by hand.") from None
            raise Fail(f"HTTP {e.code} from {url}") from None
        except TimeoutError:
            raise Fail(f"timed out after {timeout:g}s: {url}") from None
        except urllib.error.URLError as e:
            reason = e.reason
            if isinstance(reason, TimeoutError):
                raise Fail(f"timed out after {timeout:g}s: {url}") from None
            raise Fail(f"network error for {url}: {reason}") from None
        except OSError as e:  # connection reset, SSL errors, ...
            raise Fail(f"network error for {url}: {e}") from None
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise Fail(f"response from {url} is not valid JSON (first bytes: {raw[:60]!r})", EXIT_DATA) from None
    if use_cache:
        cache_put(url, body)
    return body


def _retry_after(err: urllib.error.HTTPError):
    try:
        return float(err.headers.get("Retry-After"))
    except (TypeError, ValueError, AttributeError):
        return None


# --------------------------------------------------------------------------- version helpers

def vtuple(text: str) -> tuple[int, ...]:
    nums = []
    for part in re.split(r"[.\-+]", str(text).strip()):
        m = re.match(r"\d+", part)
        if not m:
            break
        nums.append(int(m.group()))
    return tuple(nums)


def _cmp(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    n = max(len(a), len(b))
    a, b = a + (0,) * (n - len(a)), b + (0,) * (n - len(b))
    return (a > b) - (a < b)


def spec_allows(spec: str | None, version: tuple[int, ...]) -> bool | None:
    """Does a PEP 440-ish specifier set (">=3.8,<3.12", "<4.0,>=3.9") allow `version`?
    None when the specifier cannot be understood. Pre-release tags and wildcards beyond ==X.* are not modelled."""
    if not spec or not spec.strip():
        return True
    for clause in spec.split(","):
        m = re.fullmatch(r"\s*(==|!=|>=|<=|~=|>|<)\s*([0-9][0-9A-Za-z.*+!_-]*)\s*", clause)
        if not m:
            return None
        op, ver = m.groups()
        if ver.endswith(".*"):
            prefix = vtuple(ver[:-2])
            hit = _cmp(version[:len(prefix)], prefix) == 0
            ok = hit if op == "==" else (not hit if op == "!=" else None)
        else:
            c = _cmp(version, vtuple(ver))
            if op == "~=":
                base = vtuple(ver)
                ok = c >= 0 and _cmp(version[:max(len(base) - 1, 1)], base[:max(len(base) - 1, 1)]) == 0
            else:
                ok = {"==": c == 0, "!=": c != 0, ">=": c >= 0, "<=": c <= 0, ">": c > 0, "<": c < 0}[op]
        if ok is None:
            return None
        if not ok:
            return False
    return True


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pypi_name_from_url(url: str | None) -> str | None:
    """'http://pypi.python.org/pypi/django-cms' or 'https://pypi.org/project/django-cms/' -> 'django-cms'."""
    if not url or not isinstance(url, str):
        return None
    path = urllib.parse.urlparse(url).path
    m = re.search(r"/(?:pypi|project)/([^/]+)", path)
    return m.group(1) if m else None


def repo_key(url: str | None) -> str | None:
    """'https://github.com/Owner/Repo.git' -> 'github.com/owner/repo' (GitHub/GitLab/Bitbucket style hosts)."""
    if not url or not isinstance(url, str):
        return None
    p = urllib.parse.urlparse(url)
    parts = [x for x in p.path.split("/") if x]
    if not p.netloc or len(parts) < 2:
        return None
    repo = re.sub(r"\.git$", "", parts[1])
    return f"{p.netloc.lower().removeprefix('www.')}/{parts[0].lower()}/{repo.lower()}"


# --------------------------------------------------------------------------- PyPI enrichment

def summarise_pypi(payload) -> dict:
    """Reduce a PyPI JSON API payload to the fields the evaluation checklist needs."""
    if not isinstance(payload, dict) or not isinstance(payload.get("info"), dict):
        raise Fail("unexpected PyPI payload (no 'info' object)", EXIT_DATA)
    info = payload["info"]
    classifiers = [c for c in (info.get("classifiers") or []) if isinstance(c, str)]
    django = sorted({c.rsplit("::", 1)[1].strip() for c in classifiers
                     if c.startswith("Framework :: Django ::")}, key=vtuple)
    cms_cls = sorted({c.rsplit("::", 1)[1].strip() for c in classifiers
                      if c.startswith("Framework :: Django CMS ::")}, key=vtuple)
    python = sorted({c.rsplit("::", 1)[1].strip() for c in classifiers
                     if re.fullmatch(r"Programming Language :: Python :: \d+\.\d+", c)}, key=vtuple)
    times = []
    for f in payload.get("urls") or []:
        t = f.get("upload_time_iso_8601") or f.get("upload_time")
        if t:
            times.append(t)
    released = min(times)[:10] if times else None
    lic = info.get("license_expression") or (info.get("license") or "")
    if not lic or len(lic) > 60 or "\n" in lic:
        lic = next((c.rsplit("::", 1)[1].strip() for c in classifiers if c.startswith("License ::")),
                   (lic.strip().splitlines() or ["?"])[0][:40] if lic else None)
    urls = [info.get("home_page"), *((info.get("project_urls") or {}).values())]
    cms_req = None
    for r in info.get("requires_dist") or []:
        m = re.match(r"\s*django[-_]cms\s*(?:\[[^\]]*\])?\s*\(?([^;)]*)\)?\s*(;.*)?$", r, re.I)
        if m and "extra ==" not in (m.group(2) or ""):
            cms_req = m.group(1).strip().replace(" ", "")
            break
    vulns = payload.get("vulnerabilities")
    return {
        "name": info.get("name"),
        "version": info.get("version"),
        "released": released,
        "requires_python": info.get("requires_python"),
        "django_classifiers": django,
        "cms_classifiers": cms_cls,
        "python_classifiers": python,
        "license": lic or None,
        "cms_requirement": cms_req,
        "yanked": bool(info.get("yanked")),
        "known_vulnerabilities": len(vulns) if isinstance(vulns, list) else None,
        "urls": [u for u in urls if isinstance(u, str)],
        "summary": info.get("summary"),
    }


def fetch_pypi(name: str, timeout: float, use_cache: bool) -> dict | None:
    """Summary dict, or None when the project does not exist on PyPI. Network failures raise Fail."""
    payload = get_json(f"{PYPI}/{urllib.parse.quote(name)}/json", timeout, use_cache, allow_404=True)
    return None if payload is None else summarise_pypi(payload)


def repo_matches(repo_url: str | None, pypi: dict | None) -> str:
    """Does the PyPI project link back to the repo Django Packages lists? yes / no / unknown."""
    want = repo_key(repo_url)
    if not want or not pypi:
        return "unknown"
    seen = [repo_key(u) for u in pypi.get("urls", [])]
    seen = [s for s in seen if s]
    if not seen:
        return "unknown"
    return "yes" if want in seen else "no"


# --------------------------------------------------------------------------- compatibility heuristic

def compat_verdict(pypi: dict | None, pypi_name: str | None = None, today: date | None = None) -> dict:
    """HEURISTIC, metadata only: likely / unknown / unlikely for Django 5.2 + Python 3.12+ + django-cms 5.1.
    Returns {"verdict", "reasons": [...]}. It cannot see runtime breakage (removed Django APIs, bad migrations)."""
    today = today or date.today()
    reasons: list[str] = []
    if pypi_name and normalise(pypi_name) in KNOWN:
        return {"verdict": "unlikely", "reasons": [f"known problem: {KNOWN[normalise(pypi_name)]}"]}
    if pypi is None:
        return {"verdict": "unknown", "reasons": ["no PyPI release found; cannot read compatibility metadata"]}
    if pypi.get("yanked"):
        return {"verdict": "unlikely", "reasons": ["latest PyPI release is yanked"]}

    bad = []
    rp = pypi.get("requires_python")
    py_ok = [spec_allows(rp, p) for p in TARGET_PYTHONS]
    if rp and py_ok[0] is False:
        bad.append(f"requires_python {rp} excludes Python 3.12")
    elif rp and None in py_ok:
        reasons.append(f"requires_python {rp!r} not understood")
    cms_req = pypi.get("cms_requirement")
    if cms_req:
        ok = spec_allows(cms_req, TARGET_CMS)
        if ok is False:
            bad.append(f"requires django-cms {cms_req}, which excludes 5.1")
        elif ok is None:
            reasons.append(f"django-cms requirement {cms_req!r} not understood")
        else:
            reasons.append(f"django-cms requirement {cms_req} allows 5.1")
    dj = pypi.get("django_classifiers") or []
    dj_max = max((vtuple(v) for v in dj if vtuple(v)), default=None)
    strong = False
    if dj_max is not None:
        if _cmp(dj_max, (5, 2)) >= 0 or dj_max == (5,):
            strong = True
            reasons.append(f"classifiers list Django up to {'.'.join(map(str, dj_max))}")
        elif _cmp(dj_max, (4, 2)) < 0:
            bad.append(f"classifiers list Django only up to {'.'.join(map(str, dj_max))}")
        else:
            reasons.append(f"classifiers list Django only up to {'.'.join(map(str, dj_max))} (5.2 not declared)")
    else:
        reasons.append("no Django version classifiers")
    pys = pypi.get("python_classifiers") or []
    if pys and all(vtuple(p) < (3, 12) for p in pys) and not bad:
        reasons.append(f"Python classifiers stop at {pys[-1]}")
        strong = False
    age = None
    if pypi.get("released"):
        try:
            age = (today - date.fromisoformat(pypi["released"])).days
        except ValueError:
            pass
    if age is not None and age > 3 * 365:
        reasons.append(f"latest release is {age // 365} years old")
        if not strong:
            bad.append("no release for over 3 years and no explicit Django 5.2 support")
    if bad:
        return {"verdict": "unlikely", "reasons": bad + reasons}
    if strong and (age is None or age <= 2 * 365):
        return {"verdict": "likely", "reasons": reasons}
    return {"verdict": "unknown", "reasons": reasons or ["not enough metadata"]}


# --------------------------------------------------------------------------- package assembly

def _int(v, default=0) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else default


def _date10(v) -> str | None:
    return v[:10] if isinstance(v, str) and len(v) >= 10 else None


CATEGORIES = {"1": "App", "2": "Framework", "3": "Project", "4": "Other", "5": "Starter Project"}  # verified 2026-10-01


def category_name(url) -> str | None:
    m = re.search(r"/categories/(\d+)/?$", str(url or ""))
    return CATEGORIES.get(m.group(1)) if m else None


def package_from_detail(d: dict, search_hit: dict | None = None) -> dict:
    """Normalise a /packages/<slug>/ payload (and optionally its /search/ hit) to our record."""
    if not isinstance(d, dict) or "slug" not in d:
        raise Fail("unexpected Django Packages payload (package without 'slug')", EXIT_DATA)
    hit = search_hit or {}
    commits = d.get("commits_over_52") if isinstance(d.get("commits_over_52"), list) else []
    parts = d.get("participants") if isinstance(d.get("participants"), list) else []
    rec = {
        "slug": d["slug"],
        "title": d.get("title") or d["slug"],
        "page": f"https://djangopackages.org/packages/p/{d['slug']}/",
        "category": hit.get("category") or category_name(d.get("category")),
        "repo_url": d.get("repo_url"),
        "pypi_url": d.get("pypi_url"),
        "pypi_name": pypi_name_from_url(d.get("pypi_url")),
        "pypi_version_listed": d.get("pypi_version"),
        "documentation_url": d.get("documentation_url"),
        "repo_description": d.get("repo_description"),
        "repo_watchers": _int(d.get("repo_watchers")),
        "repo_forks": _int(d.get("repo_forks")),
        "last_commit": _date10(d.get("last_updated")),
        "commits_last_52_weeks": sum(c for c in commits if isinstance(c, int)),
        "participants": len(parts),
        "score": hit.get("score"),
        "usage": hit.get("usage"),
        "pypi_downloads": hit.get("pypi_downloads"),
        "last_released_listed": _date10(hit.get("last_released")),
        "grid_count": len(d["grids"]) if isinstance(d.get("grids"), list) else None,
    }
    return rec


def enrich(rec: dict, timeout: float, use_cache: bool, with_pypi: bool) -> dict:
    rec["pypi"] = None
    rec["pypi_error"] = None
    if with_pypi and rec.get("pypi_name"):
        try:
            rec["pypi"] = fetch_pypi(rec["pypi_name"], timeout, use_cache)
        except Fail as e:
            rec["pypi_error"] = str(e)
    rec["repo_match"] = repo_matches(rec.get("repo_url"), rec["pypi"]) if with_pypi else "unknown"
    if with_pypi:
        rec["compat"] = compat_verdict(rec["pypi"], rec.get("pypi_name"))
        if rec["pypi_error"]:
            rec["compat"] = {"verdict": "unknown", "reasons": [f"PyPI lookup failed: {rec['pypi_error']}"]}
    else:
        rec["compat"] = {"verdict": "unknown", "reasons": ["PyPI enrichment skipped (--no-pypi)"]}
    return rec


def fetch_package(slug_or_id: str, timeout: float, use_cache: bool, hit: dict | None = None) -> dict:
    d = get_json(f"{API}/packages/{urllib.parse.quote(str(slug_or_id))}/", timeout, use_cache)
    return package_from_detail(d, hit)


def parallel_packages(items: list, fetch, workers: int = 4) -> list:
    """Run fetch(item) with a few workers; a failing item is skipped, but if all fail the first error is raised."""
    errors: list[Fail] = []

    def run(item):
        try:
            return fetch(item)
        except Fail as e:
            errors.append(e)
            return None

    with ThreadPoolExecutor(max_workers=workers) as ex:
        out = list(ex.map(run, items))
    good = [o for o in out if o]
    if items and not good and errors:
        raise errors[0]
    return good


# --------------------------------------------------------------------------- commands

def cmd_search(a) -> dict:
    q = a.query.strip()
    if not q:
        raise Fail("empty query", EXIT_DATA)
    url = f"{API}/search/?{urllib.parse.urlencode({'q': q})}"
    hits = get_json(url, a.timeout, not a.no_cache)
    if not isinstance(hits, list):
        raise Fail("unexpected search payload (expected a JSON list)", EXIT_DATA)
    hits = [h for h in hits if isinstance(h, dict)]
    packages = [h for h in hits if h.get("item_type") == "package" and h.get("slug")][: a.limit]
    grids = [h for h in hits if h.get("item_type") == "grid" and h.get("slug")]
    recs = parallel_packages(packages, lambda h: enrich(
        fetch_package(h["slug"], a.timeout, not a.no_cache, h), a.timeout, not a.no_cache, a.pypi))
    return {"query": q, "kind": "search", "packages": recs,
            "grids": [{"slug": g["slug"], "title": g.get("title"),
                       "url": f"https://djangopackages.org/grids/g/{g['slug']}/"} for g in grids]}


def cmd_grid(a) -> dict:
    g = get_json(f"{API}/grids/{urllib.parse.quote(a.slug)}/", a.timeout, not a.no_cache)
    if not isinstance(g, dict) or not isinstance(g.get("packages"), list):
        raise Fail("unexpected grid payload (no 'packages' list)", EXIT_DATA)
    ids = []
    for u in g["packages"]:
        m = re.search(r"/packages/(\d+)/?$", str(u))
        if m:
            ids.append(m.group(1))
    scanned = ids[: a.scan]
    recs = parallel_packages(scanned, lambda i: fetch_package(i, a.timeout, not a.no_cache))
    recs.sort(key=lambda r: (r["repo_watchers"], r["commits_last_52_weeks"]), reverse=True)
    top = [enrich(r, a.timeout, not a.no_cache, a.pypi) for r in recs[: a.limit]]
    return {"kind": "grid", "grid": {"slug": g.get("slug"), "title": g.get("title"),
                                      "description": g.get("description"), "total_packages": len(ids),
                                      "scanned": len(scanned),
                                      "url": f"https://djangopackages.org/grids/g/{g.get('slug')}/"},
            "packages": top}


def cmd_grids(a) -> dict:
    d = get_json(f"{API}/grids/?limit=500", a.timeout, not a.no_cache)
    if not isinstance(d, dict) or not isinstance(d.get("results"), list):
        raise Fail("unexpected grids payload (no 'results' list)", EXIT_DATA)
    text = (a.text or "").lower()
    rows = [{"slug": g.get("slug"), "title": g.get("title"),
             "packages": len(g["packages"]) if isinstance(g.get("packages"), list) else None}
            for g in d["results"] if isinstance(g, dict) and g.get("slug")
            and text in f"{g.get('slug')} {g.get('title')} {g.get('description')}".lower()]
    return {"kind": "grids", "count_total": d.get("count"), "grids": rows[: a.limit], "matched": len(rows)}


def cmd_show(a) -> dict:
    rec = enrich(fetch_package(a.slug, a.timeout, not a.no_cache), a.timeout, not a.no_cache, a.pypi)
    d = get_json(f"{API}/packages/{urllib.parse.quote(a.slug)}/", a.timeout, not a.no_cache)
    gridnames = []
    for u in (d.get("grids") or [])[:8]:
        try:
            gd = get_json(str(u), a.timeout, not a.no_cache)
            gridnames.append({"slug": gd.get("slug"), "title": gd.get("title")})
        except (Fail, AttributeError):
            pass
    rec["grids"] = gridnames
    return {"kind": "show", "packages": [rec]}


# --------------------------------------------------------------------------- output

def _trunc(s, n):
    s = "-" if s in (None, "") else str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def render(result: dict, with_pypi: bool) -> str:
    out: list[str] = []
    kind = result["kind"]
    if kind == "grids":
        out.append(f"{result['matched']} grid(s) match (of {result['count_total']}); showing {len(result['grids'])}")
        for g in result["grids"]:
            out.append(f"  {_trunc(g['slug'], 38):<38} {_trunc(g['title'], 36):<36} {g['packages']} pkgs")
        return "\n".join(out)
    if kind == "grid":
        g = result["grid"]
        out.append(f"Grid: {g['title']} ({g['slug']}), {g['total_packages']} packages, scanned {g['scanned']}, "
                   f"sorted by GitHub watchers\n  {g['url']}")
    elif kind == "search":
        out.append(f"Search: {result['query']!r}")
    pk = result["packages"]
    if not pk:
        out.append("No packages found." + (" Try broader words, or a grid (see: grids <text>)." if kind == "search" else ""))
    else:
        head = (f"{'package':<27} {'watch':>6} {'commit':<10} {'release':<10} {'version':<9} "
                f"{'Django':<7} {'license':<12} {'repo':<4} verdict")
        out.append(head)
        out.append("-" * len(head))
        for r in pk:
            p = r.get("pypi") or {}
            dj = p.get("django_classifiers") or []
            out.append(f"{_trunc(r['slug'], 27):<27} {r['repo_watchers']:>6} {_trunc(r['last_commit'], 10):<10} "
                       f"{_trunc(p.get('released') if p else None, 10):<10} {_trunc(p.get('version'), 9):<9} "
                       f"{_trunc(dj[-1] if dj else None, 7):<7} {_trunc(p.get('license'), 12):<12} "
                       f"{_trunc(r['repo_match'], 4):<4} {r['compat']['verdict']}")
        out.append("")
        for r in pk:
            p = r.get("pypi") or {}
            out.append(f"* {r['slug']}  [{r.get('category') or '?'}]  {r['page']}")
            out.append(f"    repo: {r.get('repo_url') or '-'}   pypi: {r.get('pypi_name') or 'no PyPI link'}"
                       f"   commits/52w: {r['commits_last_52_weeks']}  contributors: {r['participants']}"
                       + (f"  usage: {r['usage']}" if r.get("usage") is not None else ""))
            if p:
                out.append(f"    requires_python: {p.get('requires_python') or '-'}   django-cms req: "
                           f"{p.get('cms_requirement') or '-'}   Django cls: {', '.join(p['django_classifiers']) or '-'}"
                           f"   vulns listed: {p.get('known_vulnerabilities')}")
            if r.get("repo_match") == "no":
                out.append("    WARNING: the PyPI project does not link to the repo listed on Django Packages;"
                           " check ownership before trusting it (typosquat risk)")
            if r.get("pypi_error"):
                out.append(f"    PyPI: {r['pypi_error']}")
            out.append(f"    compat heuristic: {r['compat']['verdict']} - " + "; ".join(r["compat"]["reasons"]))
            if kind == "show" and r.get("grids"):
                out.append("    grids: " + ", ".join(f"{g['title']} ({g['slug']})" for g in r["grids"]))
        out.append("")
        out.append("compat heuristic = metadata only (classifiers, requires_python, django-cms requirement, age) for "
                   "Django 5.2 / Python 3.12+ / django-cms 5.1. Not proof: run bin/package-trial.py, then verify.")
    if kind == "search" and result.get("grids"):
        out.append("Related grids: " + ", ".join(f"{g['slug']}" for g in result["grids"][:6])
                   + "   (bin/djangopackages.py grid <slug>)")
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="print machine-readable JSON instead of a table")
    common.add_argument("--timeout", type=float, default=15.0, help="per-request timeout in seconds (default 15)")
    common.add_argument("--no-cache", action="store_true", help="ignore and do not write the on-disk cache")
    common.add_argument("--pypi", action=argparse.BooleanOptionalAction, default=True,
                        help="enrich from the PyPI JSON API (default on; --no-pypi to skip)")
    p = argparse.ArgumentParser(prog="djangopackages.py", description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", parents=[common], help="search packages (and related grids)")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=8, help="max packages to show (default 8; the API returns 20)")
    g = sub.add_parser("grid", parents=[common], help="list the packages of a comparison grid")
    g.add_argument("slug")
    g.add_argument("--limit", type=int, default=10, help="max packages to show (default 10)")
    g.add_argument("--scan", type=int, default=60, help="max grid members to fetch before ranking (default 60)")
    gs = sub.add_parser("grids", parents=[common], help="list grids whose slug/title/description contains TEXT")
    gs.add_argument("text", nargs="?", default="")
    gs.add_argument("--limit", type=int, default=40)
    sh = sub.add_parser("show", parents=[common], help="details of one package (slug as on Django Packages)")
    sh.add_argument("slug")
    return p


def main(argv=None) -> int:
    parser = build_parser()
    a = parser.parse_args(argv)  # argparse exits 2 on usage errors
    if getattr(a, "limit", 1) < 1 or a.timeout <= 0 or getattr(a, "scan", 1) < 1:
        print("error: --limit/--scan must be >= 1 and --timeout > 0", file=sys.stderr)
        return EXIT_DATA
    try:
        result = {"search": cmd_search, "grid": cmd_grid, "grids": cmd_grids, "show": cmd_show}[a.cmd](a)
    except Fail as e:
        print(f"error: {e}", file=sys.stderr)
        return e.code
    except (KeyError, TypeError, AttributeError, ValueError) as e:  # unexpected JSON shape
        print(f"error: unexpected response data ({type(e).__name__}: {e})", file=sys.stderr)
        return EXIT_DATA
    if a.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render(result, a.pypi))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
