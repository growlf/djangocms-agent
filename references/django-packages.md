# Finding packages with Django Packages

[Django Packages](https://djangopackages.org/) is a community directory of reusable Django apps,
frameworks and tools, with "grids" that compare similar packages side by side. This file is how an agent
uses it when a user asks for functionality ("is there a package for X?", "add a blog / forms / SEO /
search / e-commerce"): search, shortlist, evaluate, recommend, **ask**, trial, install, verify, record.

**What it is not.** It is a directory and a popularity ranking, not a vetting authority. Nobody audits
the listed packages, the listing can lag PyPI, entries can be abandoned, and the Django Packages
"score" is mostly GitHub watchers. A listing says "this exists", never "this works with django CMS 5.1 /
Django 5.2". Never tell the user a package works until the trial (`bin/package-trial.py`) and the real
site's `bin/verify.sh` passed.

## Verified API facts (checked live on 2026-10-01)

Everything below was observed with real requests that day. Treat the exact numbers as a snapshot.

| Fact | Observed |
|---|---|
| Auth / key | None for GET. No key, no login, no CSRF needed for the read endpoints below. |
| API root `https://djangopackages.org/api/v4/` | JSON with `packages`, `search`, `grids`, `categories`. An older `/api/v3/` also answers (different shape: `meta`/`objects`); this skill uses v4. |
| `GET /api/v4/search/?q=TEXT` | A plain JSON **list of exactly 20** hits, relevance-ordered; `limit`/`offset` are ignored. Each hit has `item_type` (`package` or `grid`), `slug`, `title`, `category`, `score`, `usage`, `repo_watchers`, `repo_forks`, `pypi_downloads`, `last_committed`, `last_released`, `participants`, `description`, `absolute_url`, `weight`. Empty or nonsense query returns `[]` with HTTP 200. Fuzzy: `seo` also returns `django-debug-toolbar`, `django-rq`; `django cms blog` returns `django` and `django-crispy-forms`. |
| `GET /api/v4/packages/<slug>/` (also by numeric id) | Detail: `slug`, `title`, `category` (URL: 1 App, 2 Framework, 3 Project, 4 Other, 5 Starter Project), `repo_url`, `pypi_url`, `pypi_version`, `documentation_url`, `repo_description`, `repo_watchers`, `repo_forks`, `last_updated` (last commit), `last_fetched`, `commits_over_52` (52 weekly counts), `participants` (list of GitHub names), `grids` (URLs). **No** score, usage or license in the detail. Unknown slug: HTTP 404 `{"detail": "No Package matches the given query."}`. |
| `GET /api/v4/packages/?q=..` / `?slug=..` | The list endpoint (`count`, `next`, `results`, 20 per page by default) **ignores** `q` and `slug`; it is only a paginated dump of all ~5,800 packages. Do not use it for searching. |
| `GET /api/v4/grids/?limit=500` | All 381 grids in one response (about 400 KB): `slug`, `title`, `description`, `packages` (list of package URLs). |
| `GET /api/v4/grids/<slug>/` | One grid with its member package URLs (`.../packages/<id>/`). Ordering is not by quality. Fetch members by id to rank them. |
| `GET /api/v4/categories/` | 5 categories (above). |
| Rate limits | No `X-RateLimit-*`, `Retry-After` or throttle headers seen; 25 rapid requests in a row all returned 200. **No documented limit was found**, so the limit itself is unverified. Be polite (the script caches 6 h and uses 4 workers at most). Cloudflare fronts the site, so a 429/403 is possible under load. |
| robots.txt | Disallows named AI-crawler user agents (GPTBot, CCBot, anthropic-ai, Google-Extended, ...). The JSON API is a public interface and the script identifies itself as `djangocms-agent-djangopackages/1.0`, but keep volume low and do not bulk-crawl the HTML. |
| HTML search | `https://djangopackages.org/search/?q=...` returned **404** (also with a browser User-Agent). The site's search box calls `GET /search/suggestions/?q=...`, which returns an **HTML fragment** of links (`/packages/p/<slug>/`) and works without a key. Treat it as a fallback only. Package pages `/packages/p/<slug>/` and grid pages `/grids/g/<slug>/` are normal HTML. |
| Fields not in the API | License, supported Django/Python versions, release notes: get them from PyPI (JSON API `https://pypi.org/pypi/<name>/json`) or the repo. The script does this. |

If the API is down or changes shape: `bin/djangopackages.py` exits 1 (network/service) or 2
(unexpected data) with a one-line error and no traceback. Fall back, in order, to (1) the cached result
(`--no-cache` is off by default), (2) fetching the grid or package page in a browser or with a
web-fetch tool, (3) `pip index versions <name>` / the PyPI project page, (4) tell the user the directory
could not be reached and search PyPI and GitHub by hand.

## Searching

```bash
bin/djangopackages.py search "django cms blog"           # packages + related grids, with PyPI facts and a verdict
bin/djangopackages.py search seo --limit 12 --json       # JSON for further processing
bin/djangopackages.py grids cms                          # which comparison grids exist about CMS
bin/djangopackages.py grid djangocms-plugins --limit 15  # members of a grid, ranked by GitHub watchers
bin/djangopackages.py show djangocms-versioning          # one package in full
```

Options on every command: `--json`, `--limit N`, `--timeout S` (15), `--no-cache`, `--no-pypi`.
Exit codes: 0 ok (an empty result is still 0 and says so), 1 network/service problem or not found,
2 usage error or unexpected response data. From an installed skill the path is
`<skills dir>/djangocms-agent/bin/djangopackages.py`.

Search is fuzzy and returns only 20 hits. Try two or three phrasings (`djangocms blog`, `blog`,
`django cms news`) and prefer **grids**: a grid is a curated comparison of one kind of thing and ranks
far better than free text. Grids that exist today and are relevant to django CMS sites (member counts
change):

| Need | Grid slug (members) |
|---|---|
| django CMS plugins, official-ish | `djangocms-plugins` (14), `django-cms` (117, all CMS-related, noisy and old) |
| Other CMSes (alternatives, not drop-ins) | `cms` (51), `feincms` (5), `fluentcms-plugins` (16), `django-fluent` (9) |
| Blog / news | `blog` (57) |
| Forms | `forms` (108), `form-builder` (17), `contact-form` (7), `django-fobi` (2), `crispy-forms-packages` (7) |
| SEO / metadata | `seo` (20) |
| Search | `search` (30), `elasticsearch` (11) |
| E-commerce | `ecommerce` (33), `e-commerce-shop` (19), `django-shop-plugins` (20), `payment-processing` (53), `generic-payment-interfaces` (4), `invoicing` (11) |
| Rich text / editing | `wysiwyg` (41), `content-blocks` (8), `layout` (23) |
| Media | `gallery` (16), `file-managers` (46), `asset-managers` (41) |
| Other site features | `caching` (41), `globalization` (8), `filters` (16), `monitoring` (27), `help-desk` (5) |

Most grids mix Django-generic apps with CMS-specific ones. Anything whose name starts with `wagtail-`
belongs to a different CMS and does not apply.

## Reading the output

The table gives GitHub watchers, last commit, PyPI release date and version, the newest Django
classifier, license, whether the PyPI project links back to the listed repo (`repo`), and a
**compatibility heuristic**. Below the table each package has the repo and PyPI names, commits in the
last 52 weeks, contributor count, `requires_python`, the package's `django-cms` requirement and the
Django classifiers it declares.

The heuristic is deliberately blunt and reads metadata only: `unlikely` when `requires_python` excludes
3.12, when its `django-cms` requirement excludes 5.1, when it declares Django only below 4.2, when the
release is yanked, when it has had no release for three years without declaring 5.2, or when it is a
known failure from `references/plugins.md`; `likely` only when it declares Django 5.2 or newer **and**
released within two years and nothing above is wrong; everything else `unknown`. Examples seen on
2026-10-01: `djangocms-blog` 2.0.10 is `unlikely` (requires `django-cms<4.0`, classifiers stop at Django
4.2) even though it has the most CMS-blog adoption; `djangocms-frontend` and `djangocms-versioning` are
`likely`. A `likely` can still crash on import or in a migration, and a brand-new package can be
`likely` with zero users, so always weigh the adoption columns too.

## Evaluation checklist

Shortlist two or three, fill this in for each, and show it to the user. A single failed hard item
(marked **H**) removes a candidate unless the user accepts the cost.

1. **H: Django 5.2 and Python 3.12-3.14.** PyPI classifiers (`Framework :: Django :: 5.2`),
   `requires_python`, and the CHANGELOG or CI matrix in the repo. No 5.x classifier is a warning, not a
   verdict; the trial decides.
2. **H: django-cms 5.1.x.** Is it a `djangocms-*` plugin or apphook app, and what does it require
   (`django-cms>=...`)? Many packages still pin `django-cms<4` (the 3.x era). A generic Django app
   (no `djangocms` in the name) usually works but will not appear in the CMS plugin picker or toolbar
   unless it ships a `cms_plugins.py`, `cms_apps.py` or `cms_toolbars.py`.
3. **Maintenance.** Last release date, last commit, commits in the last 52 weeks, number of contributors,
   whether recent issues get answers, how many are open and how old. One maintainer plus no commits for
   a year is a risk to name to the user.
4. **License.** Say what it is. GPL/AGPL in a site the user distributes or offers over a network is a
   decision for the user, not for you.
5. **Migrations.** Does it ship its own (the trial prints this)? Models that change under you are a
   long-term cost; reusing djangocms-alias or a plain plugin is cheaper than a new app with tables.
6. **Extra services, JS and CDN.** The default site works on a LAN with no CDN. Anything that needs a CDN
   script, Google/Mapbox keys, Redis, Elasticsearch, Celery or a SaaS API (cf. djangocms-googlemap in
   `references/plugins.md`) must be called out, with the offline alternative if there is one.
7. **Known findings.** Cross-check `references/plugins.md`: `djangocms-form` is not on PyPI,
   `djangocms-social` crashes Django 5.2, `djangocms-text-ckeditor` is superseded by `djangocms-text` and
   must stay out of `INSTALLED_APPS`, `djangocms-snippet` does not fit versioning, three
   bootstrap5 contrib apps fail. A candidate that depends on a "do not enable" package is a conflict.
8. **Interaction with djangocms-versioning.** A model that is edited per page should be versioned
   (that needs a versioning registration in the package's `cms_config.py`; read its docs, do not assume); an unversioned plugin is
   live the moment an editor saves it. Say which applies.
9. **Fit.** Does it solve what the user asked, or is it a different kind of thing (a whole CMS, a
   headless starter project)? Is there a simpler route: the Raw HTML block, a Bootstrap grid class, an
   existing plugin?

## Supply-chain care

- **Verify identity.** The PyPI project must belong to the repo Django Packages lists. The table's
  `repo` column does a mechanical check (`yes` = PyPI links to that GitHub repo, `no` = it links
  elsewhere, `unknown` = nothing to compare). Treat `no` and `unknown` as stop-and-look: open the PyPI
  page and the repo, compare names and owners, check the repo's `pyproject.toml` name. Typosquats
  (`djangocms-bllog`, `django-cms-blog` vs `djangocms-blog`) and abandoned-name takeovers are real.
- **Pin exact versions** in `requirements.txt` (`name==x.y.z`), never a range, once the trial passed with
  that version.
- **Install first into a throwaway environment** (`bin/package-trial.py`), never into the user's real venv
  as an experiment. The trial installs wheels only by default so no build script runs; `--allow-sdist`
  is an explicit decision.
- **Never install anything unless the user asked.** Searching and evaluating is free; installing is a
  change. Recommend, ask, and wait for a yes.
- **Report what it pulls in** (the trial lists new packages and fails if the candidate would change a
  version the default site pins) and **its license**, and mention any `known_vulnerabilities` PyPI lists.
- Do not run code from the package's README "quick start" blindly; read it first.

## The trial: `bin/package-trial.py`

```bash
bin/package-trial.py djangocms-markdown --app djangocms_markdown          # a clean PASS (2026-10-01)
bin/package-trial.py djangocms-blog==2.0.10 --app djangocms_blog --keep   # FAIL at the candidate install
bin/package-trial.py NAME --app pkg.apps.PkgConfig --settings "PKG_OPTION = True" --requirement other-dep
```

It scaffolds the default site into a temp directory (`bin/new-site.py --no-venv`), makes a venv, installs
the pinned `requirements.txt`, installs the candidate, appends the app and your settings, then imports the
app and runs `manage.py check`, `migrate --noinput` and `makemigrations --check --dry-run` for the
package's own app labels only (the base site's bootstrap5 apps always show drift). It lists the CMS
plugins and apphooks the package registered, the packages it pulled in, and fails if it moved a pinned
version or `pip check` found a new conflict. It deletes the temp dir unless `--keep` (or `--workdir`) and
never touches a real project. Exit 0 PASS, 1 FAIL (the failing step and an output tail are printed),
2 usage error. About 25 seconds for a small package.

**PASS means only** install, import, `check`, `migrate` and no migration drift worked. It does not show
that the plugin renders, that the editor UI works, that it fits the theme, that its static files load, or
that it is safe. `--app` is guessed from the PyPI name if you omit it; if the import step fails with
"No module named", look at the wheel's top-level package (`pip show -f NAME`) and pass `--app`.
Packages that need settings before `check` passes (API keys, backends) need `--settings`; a FAIL without
the right settings is not proof the package is bad. The trial appends the app after
`djangocms_versioning`; ordering rules for the real site are below and are not exercised.

## Installing and configuring in a real site (only after the user says yes)

1. **Branch or checkpoint first.** In the user's project, work on a branch or a clean commit.
2. **Pin.** Add `name==x.y.z` (the version the trial passed) to `requirements.txt`, plus the transitive
   pins the trial reported if the project pins everything. Install into the project's venv from that file.
3. **`INSTALLED_APPS`.** Add the app in the project's `settings.py`. Order rules:
   `djangocms_admin_style` before `django.contrib.admin`; keep the default site's order of its own
   entries (`djangocms_text`, the project app, then `cms`); `cms`, `menus`, `treebeard`, `sekizai` before the plugins; `djangocms_versioning`
   after `djangocms_alias` (it is the last CMS app in the default site; keep it last unless the package's
   docs say otherwise); an app that overrides templates or static files of another must come first.
   Packages that document their own order (for example needing `filer` and `easy_thumbnails`) win over
   this list. Add each sub-app (`pkg.contrib.x`) individually.
4. **Settings and middleware.** Only the settings the package's docs name; **verify each one in the
   installed package** (grep it) before using it, do not invent any. Some packages need a context
   processor, middleware or a `urls.py` include; apphook packages need `ApphookReloadMiddleware`
   (already first in the default site) and a page with the apphook attached.
5. **Migrations.** `manage.py migrate`. If the package has models, `manage.py makemigrations --check
   <your own apps>` must stay clean. Do not edit `site-packages`.
6. **Placeholders and templates.** The default site's `CMS_PLACEHOLDER_CONF` has no plugin allow-lists, so
   a new plugin appears in every slot. If the project restricts plugins per slot, add the new plugin's
   class name. Add the template or `{% placeholder %}` the feature needs to `CMS_TEMPLATES` templates.
   For an apphook (blog, shop), create the page and attach the apphook; the CMS must be in the default
   language the package ships translations for.
7. **Static files and theme.** If the package ships CSS/JS, make sure `collectstatic` works and nothing
   loads from a CDN. The default site is Bootstrap 5.3 with its own `static/css/site.css` tokens; style
   the package's markup with Bootstrap classes or small overrides in `site.css`, not by adding a second
   framework. Check mobile width and dark mode.
8. **Tests.** Add a small test in the project's own app that creates a page using the feature (or the
   plugin through `add_plugin`) and renders it, so a later upgrade is caught.
9. **Verify.** Run the project's `bin/verify.sh`, run `scripts/visual_check.py` on a page that uses the
   feature (desktop and mobile), and **look at the screenshots**. Log in to the CMS toolbar and add the
   plugin through the editor UI at least once if you can; say so if you could not.
10. **Record.** Add a row to `references/plugins.md` (in the skill repo, not the user's site): package,
    `WORKS` / `FAILS` / `check + migrate only`, and a note with the date and the versions (django-cms,
    Django, package) it was tried on and what "works" covered. A failed trial is worth recording too, so
    nobody tries it again.
11. **Report** what was and was not verified, with the exact versions, license and extra dependencies.

## The workflow in one line

search -> shortlist 2-3 with the checklist -> tell the user and recommend one -> **ask before installing**
-> `package-trial.py` -> install in the real site -> `bin/verify.sh` + screenshots -> record in
`references/plugins.md`.
