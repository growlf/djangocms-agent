# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Fixed (independent verification of the default site and scaffolder)
- `scripts/visual_check.py --login` never logged in yet printed `RESULT: PASS` (`get_by_label/get_by_role` do not take `timeout`, the fallback clicked `button[type=submit]` while Django admin uses `input[type=submit]`, and a bare `except: pass` hid it). It now fills `#id_username`/`#id_password`, submits, waits for navigation and FAILS (exit 1, `ISSUE: login ...`) when the login form or a `/login` URL is still showing, no form is found, or the markup differs. Tests use a stub Django-admin-like login server. The generated `bin/verify.sh` text says the logged-in step asserts a real login and a failure makes `VERIFY RESULT: FAIL`.
- Default site: the `(overview)` label inside the active dropdown item is readable (was 1.13:1 light, 1.22:1 dark); blockquote `cite` uses the muted token (was Bootstrap grey, 3.81:1 dark).
- `bin/new-site.py` interactive mode re-asks each question until the answer is valid (name validated immediately); non-TTY still exits 2.
- Seed commands set the django Site name to the site name and the domain to `SITE_DOMAIN` (default `localhost`) instead of `example.com`.

### Added (native Docker + PostgreSQL in every scaffolded site)
- `assets/default-site/`: `Dockerfile`, `docker-compose.yml` (postgres:16-alpine `db`, gunicorn `app`, named volumes, healthchecks, `APP_PORT` default 8889), `docker/entrypoint.sh`, `dockerignore.template` (written as `.dockerignore`), `bin/docker-up.sh`, `bin/docker-down.sh`, `bin/docker-env.sh`, `__PROJECT_NAME__/health.py` (`/health/`), `starter/tests_docker.py`, and a `seed` management command (`seed_pages` then `seed_site`; the old commands still work).
- Settings: DB switched by `DB_ENGINE` (SQLite stays the default), WhiteNoise after `SecurityMiddleware` with `ApphookReloadMiddleware` still first, `STORAGES`, `STATIC_ROOT` created at import (no "No directory at: staticfiles/" warning), `DJANGO_SERVE_MEDIA` media route for DEBUG off, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_BEHIND_PROXY`. gunicorn runs with `--no-control-socket`. Requirements add `psycopg[binary]==3.3.6`, `gunicorn==26.2.0`, `whitenoise==6.12.0` (installed on Python 3.12 and 3.14).
- `bin/new-site.py`: Docker files are included by default; `--no-docker` omits them and the Docker sections of the generated README/AGENTS.md. `--no-venv`/`--skip-install` unchanged. The scaffolder seeds with `manage.py seed`, and the Next steps output documents `bin/docker-up.sh`, the 8889 default and the CSRF origin note. `.env.example` now gets `__PROJECT_NAME__` substituted.
- Docs: `references/new-site.md` (flags, what Docker adds, ports, CSRF note, slug derivation, skill-relative paths), `references/project-setup.md` (container settings, media story, WhiteNoise placement, gunicorn flag), default-site README, generated README/AGENTS.md.
- Tests: Docker files in the plan and on disk by default, `--no-docker`, executable and `bash -n` clean scripts, `docker compose config` (skipped without docker), generated starter tests for the DB switch, middleware order, health, media flag.

### Added (finding packages on Django Packages)
- `bin/djangopackages.py` (stdlib, Python 3.12+): `search`, `grid`, `grids`, `show` with `--json`, `--limit`, `--timeout`, `--no-cache`, `--no-pypi`. Uses the key-less Django Packages API v4, enriches each package from the PyPI JSON API (version, release date, `requires_python`, Django classifiers, license, `django-cms` requirement, repo-link check) and prints a comparable table with a labelled compatibility heuristic (likely / unknown / unlikely for Django 5.2, Python 3.12+, django-cms 5.1). Clear errors for timeouts, 429, 404 and malformed JSON (exit 1 network/service, 2 usage/data), a User-Agent naming the skill, a 6 hour on-disk cache.
- `bin/package-trial.py`: builds a throwaway site from `assets/default-site` (via `bin/new-site.py --no-venv`), installs the pinned requirements and the candidate (wheels only by default), reports what it pulled in and any changed pin, appends the app, then import / `check` / `migrate` / `makemigrations --check` for the package's own labels, lists the plugins and apphooks it registered, cleans up unless `--keep`. PASS is documented as check + migrate + import only.
- `references/django-packages.md`: verified API facts (2026-10-01), grids relevant to django CMS sites, evaluation checklist, supply-chain section, trial and real-site install/configure/verify/record procedure. `references/plugins.md` gains rows for djangocms-markdown (check + migrate only) and djangocms-blog (fails: needs `django-cms<4`).
- `SKILL.md` and `agents/djangocms-agent.md`: triggers and a short "Finding packages" workflow (search, shortlist, recommend, ask, trial, install, verify, record; never claim it works before the trial and verify).
- Tests: `tests/test_djangopackages.py`, `tests/test_package_trial.py`, recorded fixtures in `tests/fixtures/`; live smoke tests only with `DJANGOPACKAGES_LIVE=1` / `PACKAGE_TRIAL_LIVE=1`.

### Changed (new-site friction found by an end-to-end test)
- `bin/new-site.py` preflights Playwright at startup, before creating anything: `playwright` importable with `PLAYWRIGHT_PYTHON` (else `python3`) and chromium installed. If not, a non-fatal NOTICE prints the one-time scratch-venv setup; `--require-playwright` makes it fatal (exit 2). Workflow order in `SKILL.md`, `agents/djangocms-agent.md` and `references/new-site.md` is now: ask, check Playwright, scaffold, verify.
- `DJANGO_DEBUG_TOOLBAR` switch in `settings_fragment.py` (`USE_DEBUG_TOOLBAR`): default on with DEBUG; `0/false/no/off` removes the app, middleware and `/__debug__/` url together. Generated `bin/verify.sh` runs its server with it off, so the debug-toolbar handle (not the CMS toolbar) no longer overlaps screenshots. Documented in the default-site README, `references/project-setup.md`, `.env.example`.
- Generated `bin/verify.sh` prints per step what it covers, and for the visual step the URLs, what is asserted and what is not checked.
- `scripts/visual_check.py` now fails on horizontal overflow (`documentElement.scrollWidth > clientWidth + 1`), with unit and browser tests.
- Docs: which URL/port to report (first free port >= 8000, exact run command), admin login reported as printed and never written to a file, link-mode installs symlink `bin/ assets/ references/ scripts/` into the clone, `treebeard.E001` documented once in the generated README. The scaffolder's suggested port now starts at 8000.

### Added (new-site scaffolder)
- `bin/new-site.py` (stdlib, Python 3.12+): `--name`, `--purpose`, `--site-name`, `--parent-dir`, `--license`, `--author`, `--no-venv`/`--skip-install`, `--no-opskit`, `--dry-run`, `--yes`. Name and purpose are required from the human (interactive prompt on a TTY, exit 2 otherwise). Validates names, never overwrites, refuses a non-empty target. Writes the default site with `__PROJECT_NAME__`/`__SITE_NAME__` substituted in contents and paths, wsgi/asgi/`__init__`, FOSS files, AGENTS.md + thin CLAUDE.md with the purpose, README, `.opskit/pack.yml` (file only, no opskit command), `scripts/visual_check.py`, `bin/verify.sh`; then venv, install, migrate, `admin` superuser with a random one-time password, seed, `git init` + first commit.
- `assets/foss/`: governance templates (from the foss-init conventions) and licenses MIT, ISC, BSD-3-Clause, Unlicense; `assets/default-site/.env.example`.
- Generated `bin/verify.sh`: check, `makemigrations --check` for own apps, tests, seed idempotency, Playwright `visual_check.py` desktop + mobile on key URLs; ends with `VERIFY RESULT: PASS|FAIL|INCOMPLETE`.
- `references/new-site.md` and the "New site" workflow in `SKILL.md` and `agents/djangocms-agent.md`: ask for name and purpose, scaffold, verify and look at screenshots, report honestly.
- `skills/djangocms-agent/bin` symlink so the scaffolder is reachable from link and copy installs (tested).
- `tests/test_new_site.py`.

### Fixed
- `assets/default-site/settings_fragment.py` now includes `LocaleMiddleware` after `SessionMiddleware` (as `references/project-setup.md` says); both settings and urls fragment docstrings no longer mention scaffold placeholders.

### Added
- `assets/default-site/`: a complete, copyable Bootstrap 5.3 default site ported from the verified testsite build: templates (base, landing, standard, menu), static (site.css, theme.js, vendored Bootstrap 5.3.3 with its MIT LICENSE), a `starter` app (generic trusted-editors-only `HtmlBlock` plugin, `seeding.py`, idempotent `seed_pages`/`seed_site`, 20 tests), `settings_fragment.py`, `urls_fragment.py`, context processor, pinned `requirements.txt`. Project-specific tokens are `__PROJECT_NAME__` and `__SITE_NAME__` (a scaffold script is a later change). Testsite-only parts (testlog app, findings text) were removed and `CMS_PLACEHOLDER_CONF` now names `feature_1..3`.
- `skills/djangocms-agent/assets` symlink so installed skills (link and copy modes) can read the assets; installer tests cover both modes, doctor and uninstall.

### Fixed (found by the default-site build)
- `references/plugins.md` rewritten as a works/fails matrix: bootstrap5 passes only for its base app and the alerts/badge/card/collapse/content/jumbotron/listgroup/picture/tabs/utilities contrib apps; `bootstrap5_grid`, `bootstrap5_link`, `bootstrap5_carousel` fail, djangocms-snippet is unsuitable, text-ckeditor must stay out of `INSTALLED_APPS`; bootstrap5 quirks (picture replaces stock picture, no default classes via `add_plugin`, unfixable migration drift, Google Map needs an API key).
- `SKILL.md` gotchas: `get_placeholders(lang)` sees only published content (use `admin_manager=True`); `create_versions` for pre-versioning content; the `"python-api"` string cannot publish, a real user object is required.
- `references/project-setup.md`: debug toolbar inserted at index 1 and DEBUG-only (index 0 broke the ApphookReloadMiddleware-first rule); TEMPLATES `loaders` conflicts with `APP_DIRS: True`; admindocs prefix (`admin/docs/` vs Django's `admin/doc/`); toolbar settings note that `CMS_TOOLBAR_REQUIRE_SUPERUSER`/`ANONYMOUS_EDIT` do not exist.
- `references/templates-and-theme.md` rewritten for the Bootstrap theme (hamburger and Bootstrap are now implemented); the checklist ticks only what was run and lists what was not (logged-in toolbar and `/admin/docs/` in a browser, numeric contrast).

### Removed
- `references/default-theme.html`, `default-theme-two-column.html`, `default-menu.html`, `default.css`: superseded by `assets/default-site/` (no duplicated copies to drift).

### Changed
- Default theme reference files replaced with the version built and checked in the testsite project (all pages passed `visual_check.py` on desktop and mobile): `default-theme.html` (base), new `default-theme-two-column.html` and `default-menu.html`, and `default.css` (now `--site-*` tokens, dark mode, `:focus-visible`, skip link, restored text spacing, styled nested menu with dropdowns). The `netyeti` prefix is gone. `templates-and-theme.md` rewritten to match, with a verification checklist that only ticks what was run; hamburger and Bootstrap compatibility are listed as not implemented.
- `references/project-setup.md`: new "Static files and site name" section (`STATICFILES_DIRS`, `STATIC_ROOT`, `SITE_NAME` + context processor).
- Fixed in the old reference theme: undefined `{{ site_name }}`, claimed-but-missing dark mode, menu selectors that never matched `{% show_menu %}` output, `* { margin:0; padding:0 }` stripping content spacing, links with no underline, hardcoded `cms-home` class, always-on sidebar, bare `<li>` directly in `<nav>`, no `{% block %}` hook, `default.html` vs `default-theme.html` naming, `CMS_TEMPLATES` entry that was not a template path.

### Fixed (found by the testsite exercise, 2026-09-30)
- `skills/djangocms-reviewer/SKILL.md`: no longer hardcodes `language="en-us"` (it must match the project's `LANGUAGES`); adds apphook checks (`app_name`/`apphook_namespace`, `ApphookReloadMiddleware`, `reload_urlconf()` in tests) and seed-script checks (slug+language idempotency, `atomic()`, `created_by`).
- `skills/djangocms-agent/` now contains `references` and `scripts` symlinks to the repo-level directories. In link-mode installs only `SKILL.md` was visible, so `scripts/visual_check.py` and every `references/` link it names appeared missing.
- `SKILL.md` gotchas: project-specific language codes, `created_by=None` crash, seed idempotency keyed on slug+language inside `atomic()`, optional djangocms-versioning, Python 3.14 installer failure, upstream `treebeard.E001`.
- `references/cms-api-cheatsheet.md`: new Apphooks section (`app_name`/`apphook_namespace`, `ApphookReloadMiddleware`, `reload_urlconf()` in tests).

### Added
- `references/project-setup.md`: verified `MIDDLEWARE` section (the docs listed none; a project built from them lacked `SecurityMiddleware`, `XFrameOptionsMiddleware`, `LocaleMiddleware` and `ApphookReloadMiddleware`) and a production hardening checklist checked with `manage.py check --deploy`.

## 0.5.0 - 2026-09-30

### Fixed (found by building a scratch django-cms 5.1.3 project from the docs)
- `show_menu` does NOT require `cms.context_processors.cms_settings` (it falls back to its own renderer); it needs pages with `in_navigation=True`. The earlier claim was wrong.
- The documented `INSTALLED_APPS` omitted `django.contrib.sites` (+ `SITE_ID`): startup crashed.
- `docutils` is not installed with Django; admindocs needs `pip install docutils`.
- Plugin list: `djangocms-form` does not exist on PyPI; `djangocms-social` 0.4a1 crashes on Django 5.2. Removed. Alias/picture/video/file/style/bootstrap5/googlemap pass check + migrate.
- `create_page` creates a draft under djangocms-versioning; publishing, `in_navigation` and homepage recipes documented.
- Both menu variants and the page template now verified to render.

### Added
- `bin/install.py`: idempotent installer for Claude Code, OpenCode and Crush (`--project`/`--global`, `--link`/`--copy`, `--dry-run`, `--uninstall`, `doctor`), lockfile-tracked so it only ever touches its own files; 20 tests.
- `agents/djangocms-agent.md` and `agents/djangocms-reviewer.md`: canonical subagent definitions (OpenCode format is generated from them).
- `.opskit/pack.yml`: OpsKit member manifest.
- `references/project-setup.md`, `references/templates-and-theme.md`, `references/plugins.md`.

### Changed
- `SKILL.md` slimmed from ~420 to ~75 lines; detail moved to `references/` (read on demand).
- `scripts/visual_check.py` rewritten: real exit codes (0 pass / 1 issues / 2 error), console-error and failed-subresource detection, exact 404 detection (no more false 404s on pages that mention "not found"), `--mobile`, `--expect-text`, `--login`; unit tests added.


### Fixed (earlier review rounds)
- Removed duplicate sections from djangocms-agent SKILL.md (deduplicated ~160 lines)
- Removed invalid settings: `CMS_TOOLBAR_ANONYMOUS_EDIT`, `CMS_TOOLBAR_REQUIRE_SUPERUSER`, `CMS_TOOLBAR_URL__EDIT_ON`, `CMS_TOOLBAR_URL__EDITMODE`
- Removed non-existent setting `CMS_DEFAULT_INTENT` from all docs
- Corrected `{% show_menu %}` guidance (`menus.context_processors.menus` does not exist; see Unreleased for the later correction that `cms_settings` is recommended but not required)
- Aligned references and adapters with django-cms 5.x (replaced all 4.x references)
- Replaced `djangocms-text-ckeditor` with `djangocms-text` (correct package for CMS 5.x)
- Removed references to 8 sub-skills that do not exist
- Removed further non-existent settings from references: `CMS_SEO_FIELDS`, `CMS_TOOLBAR_URL__PASTE`, `CMS_NAVIGATION_EXTENDERS`
- Fixed root-redirect example that redirected `/` to itself; relabelled unproven template/checklist sections as unverified
- Gated debug toolbar configuration on `DEBUG` flag; removed unsafe "Safe for production" claim

### Verification status
- Proven (scratch project, cms 5.1.3 / Django 5.2.17, 2026-09-30): documented settings boot with `sites` added; `show_menu` and the hand-rolled menu render; versioning publish recipe; installer output is discovered by OpenCode (both skills once, from `.claude/skills`; `djangocms-agent` loads as a subagent).
- Not proven: Crush discovery (not run on purpose), plugin rendering (only check/migrate), mobile layout, `CMS_TOOLBAR_*` behaviour.
