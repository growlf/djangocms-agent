# Default site template (Bootstrap 5.3, django CMS 5.1)

A complete, copyable DjangoCMS 5 site: landing and standard page templates, a Bootstrap navbar with a
working hamburger and dropdowns, light/dark mode, a seeded "Style & Capabilities" page that renders every
verified plugin, and idempotent seed commands that publish through djangocms-versioning.
It was built and verified in a scratch project (django-cms 5.1.3, Django 5.2.17) and ported here.

## Placeholders

`bin/new-site.py` (see `references/new-site.md`) is that scaffold: it copies this directory into a new project and substitutes two tokens:

| Token | Meaning | Where |
|---|---|---|
| `__PROJECT_NAME__` | Python package with `settings.py`/`urls.py`; also the name of the `__PROJECT_NAME__/` directory | `settings_fragment.py`, `manage.py`, `__PROJECT_NAME__/` |
| `__SITE_NAME__` | Human-readable name shown in navbar, title and footer | `settings_fragment.py` (`SITE_NAME`) |

## Layout

| Path | Copy to | Notes |
|---|---|---|
| `templates/` | `templates/` | `base.html` (shell), `landing.html`, `standard.html`, `menu/menu.html`, `menu/footer_menu.html` |
| `static/` | `static/` | `css/site.css`, `js/theme.js`, vendored `vendor/bootstrap/` (5.3.3 CSS + bundle JS, MIT `LICENSE` included; no CDN) |
| `starter/` | `starter/` | app: `HtmlBlock` plugin, `seeding.py` helpers, `seed` (= `seed_pages` + `seed_site`), `seed_pages`, `seed_site`, tests |
| `__PROJECT_NAME__/context_processors.py` | `<project>/context_processors.py` | exposes `SITE_NAME` as `site_name` |
| `settings_fragment.py` | `<project>/settings.py` | the complete settings module (or merge sections) |
| `urls_fragment.py` | `<project>/urls.py` | admindocs, admin, debug toolbar (DEBUG and `DJANGO_DEBUG_TOOLBAR`), cms.urls last |
| `manage.py` | `manage.py` | standard, points at `__PROJECT_NAME__.settings` |
| `Dockerfile`, `docker-compose.yml`, `docker-compose.dev.yml`, `docker/*.sh`, `bin/docker-*.sh`, `bin/dev-*.sh`, `bin/pin-images.sh`, `bin/pin_images.py` | same paths | Docker + PostgreSQL production stack, standalone dev stack, backup/restore, digest pins (omitted by `new-site.py --no-docker`) |
| `bin/release.sh` | same path | `vX.Y.Z` release helper (refreshes pins when present, tests, `VERSION`, `CHANGELOG.md`, commit, tag; never pushes) |
| `templates/djangocms_googlemap/`, `templates/djangocms_video/`, `static/js/googlemap-guard.js` | same paths | keyless-map fail-safe and video fallback link |
| `dockerignore.template` | `.dockerignore` | build-context excludes (secrets, venv, db, media) |
| `__PROJECT_NAME__/health.py` | `<project>/health.py` | `/health/` for container healthchecks |
| `requirements.txt`, `requirements-dev.txt` | same paths | pinned production set; dev adds `django-debug-toolbar` (`-r requirements.txt`) |
| `env.example.template`, `gitignore.template` | `.env.example`, `.gitignore` | environment variables; ignore rules |

`wsgi.py`, `asgi.py` and `__init__.py` for the project package are the unmodified `django-admin startproject` output (`WSGI_APPLICATION` refers to `wsgi.py`); the scaffold must create them.

`settings_fragment.py` and `urls_fragment.py` are named so they are not mistaken for importable modules of
this repo; they are plain Python and compile as-is.

## Running the result

    pip install -r requirements-dev.txt   # requirements.txt alone = production
    python manage.py migrate
    python manage.py createsuperuser
    DJANGO_DEBUG=1 python manage.py seed_pages     # Home (landing template), set as homepage
    DJANGO_DEBUG=1 python manage.py seed_site      # landing content, About, Style & Capabilities
    # both also set the django Site: name = SITE_NAME, domain = $SITE_DOMAIN (default localhost), not example.com
    DJANGO_DEBUG=1 DJANGO_SECRET_KEY=dev python manage.py runserver 8005
    DJANGO_DEBUG=1 DJANGO_SECRET_KEY=dev python manage.py test starter

## Docker + PostgreSQL

    bin/docker-up.sh               # creates .env (random secrets), builds, starts, waits healthy, prints the URL
    APP_PORT=8891 bin/docker-up.sh -p other   # another host port / compose project name
    bin/docker-down.sh             # stops, keeps volumes; --volumes deletes this project's volumes

Compose project `__PROJECT_NAME__`: `db` (postgres:16-alpine, no host port) and `app` (gunicorn, WhiteNoise,
DEBUG and the debug toolbar off, non-root) on `127.0.0.1:${APP_PORT:-8889}`. `DB_ENGINE=postgres` selects
PostgreSQL; unset keeps SQLite so `runserver` and `bin/verify.sh` are unchanged. With PostgreSQL the default cache
is a shared database table (all gunicorn workers see a publish at once; `DJANGO_CACHE=locmem|db`). `SEED_ON_START=1` runs
`manage.py seed --first-run-only` at start (a fresh database only; editors' emptied placeholders are not refilled).
`bin/dev-up.sh` starts the separate dev stack (`<project>-dev`, 127.0.0.1:8880). `bin/docker-backup.sh` and
`bin/docker-restore.sh` back up and restore database and media. Images are pinned by digest (`bin/pin-images.sh`,
refreshed by `bin/release.sh`); behind a TLS proxy `DJANGO_BEHIND_PROXY=1` makes the cookies Secure. Admin login needs the browsed origin in `DJANGO_CSRF_TRUSTED_ORIGINS` (the compose
default follows `APP_PORT` for localhost). `DJANGO_SERVE_MEDIA=1` serves uploads from Django when DEBUG is off.
The generated README documents backup, restore, reset and proxy use; `references/project-setup.md` in the skill
explains each setting.

## Login throttling (django-axes)

`axes` (pinned `django-axes==8.3.1`) counts failed logins in the database (shared by all gunicorn workers, SQLite and
PostgreSQL alike). After `DJANGO_LOGIN_FAILURE_LIMIT` (5) failures the username + client IP is locked for
`DJANGO_LOGIN_COOLOFF_MINUTES` (60; 0 = until reset) and gets a 429 page, even with the right password. Unlock with
`python manage.py axes_reset` (also `axes_reset_ip`, `axes_reset_username`, `axes_reset_ip_username`). Limit 0 disables it;
`DJANGO_LOGIN_LOCKOUT_BY=ip` is the stricter mode. The client IP is `REMOTE_ADDR`; `X-Forwarded-For` is trusted only with
`DJANGO_BEHIND_PROXY=1` (`__PROJECT_NAME__/security.py`, `DJANGO_PROXY_COUNT` hops from the right). Settings block and order
rules: `references/project-setup.md`. Tests: `starter/tests_throttle.py`.

## Theme toggle

The header button (`data-theme-toggle`, `static/js/theme.js`) flips light/dark, stores the choice in `localStorage`
(`theme`) and otherwise follows the OS, live. The script runs in `<head>` (no flash); without JavaScript the
`prefers-color-scheme` rule in `site.css` applies and the button stays hidden.

## Debug toolbar handle

With `DJANGO_DEBUG=1` pages show a small green tab with a dark glyph on the right edge. That is the
**django-debug-toolbar handle, not the CMS toolbar** (anonymous visitors get no CMS toolbar markup). It only
exists when DEBUG is on. Set `DJANGO_DEBUG_TOOLBAR=0` (or `false`/`no`/`off`) to remove it: the app, the
middleware and the `/__debug__/` url are all dropped together (`USE_DEBUG_TOOLBAR` in `settings.py`).
`bin/verify.sh` uses that switch so screenshots are clean.

`seed_site --reset` clears and refills the placeholders that command owns.

## Seed command rules

- Idempotent: pages are looked up by `PageUrl(slug, language)`, never by title; placeholders are only
  filled when empty.
- Atomic: each page's create / plugin / homepage work is one `transaction.atomic()`.
- Published content is never edited in place: `editable_content()` makes a draft copy, the seed fills it,
  `publish()` publishes once (a second run adds no versions). `seed --first-run-only` skips a seeded site.
- Versioning: `create_page` makes a DRAFT, so `starter/seeding.py` works through
  `PageContent.admin_manager` (the default manager only sees published content) and publishes with a
  real user object (`get_user()`; the string `"python-api"` cannot publish, so an inactive system user
  is created when no superuser exists).
- Content created before djangocms-versioning was installed has no `Version` rows and renders as
  missing. Either rely on `publish()` (it creates the Version), or run once:
  `python manage.py create_versions --state published --username <superuser>`.
- Language is `LANG = "en"` in `starter/seeding.py`; it must match `LANGUAGES`.

## HtmlBlock plugin: trusted editors only

`starter.HtmlBlock` ("Raw HTML block (trusted)") renders its `html` field with `|safe`. djangocms-text
sanitises its HTML (strips forms and `data-*` attributes), so Bootstrap components that need them go
through this plugin. Anyone allowed to add it can inject arbitrary HTML and script into every visitor's
browser (stored XSS by design). Grant it only to editors you trust as much as developers; restrict it
with `CMS_PLACEHOLDER_CONF[...]['plugins']` allow-lists or Django permissions if untrusted users can edit.

## Known upstream limits (do not try to fix in the project)

- `makemigrations --check` reports pending changes inside the installed `djangocms_bootstrap5.contrib.*`
  packages; fixing it would mean editing site-packages. `makemigrations --check starter` is clean.
- Plugins created through `add_plugin` get no default CSS classes (only the admin form adds them), so
  `seed_site` passes explicit `attributes` classes.
- Google Map needs `GOOGLE_MAPS_API_KEY` (and internet); the seed adds the sample map only when it is set, and
  without a key the map plugins are not offered to editors (an existing map shows a notice).
- Video embeds need internet access to show their player.
- `references/plugins.md` lists which plugin packages work and which fail on this stack.
