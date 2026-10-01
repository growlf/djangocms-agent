## PROJECT SETUP (DEFAULT SETTINGS)

When creating a new DjangoCMS project, always include these settings in `settings.py`:

### TEMPLATES (explicit loaders, no APP_DIRS)
Pick ONE way to find templates. `APP_DIRS: True` and an explicit `OPTIONS['loaders']` list are mutually exclusive: Django raises `ImproperlyConfigured` if both are set. Either works for CMS plugins as long as the app_directories loader is present; the default site uses explicit loaders and leaves `APP_DIRS` out. (If you do not need to customise loaders, `'APP_DIRS': True` with no `loaders` key is the simpler choice.)
```python
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        # no 'APP_DIRS': it conflicts with 'loaders' below
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'sekizai.context_processors.sekizai',
                'cms.context_processors.cms_settings',
            ],
            'loaders': [
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',  # REQUIRED for CMS plugin templates
            ],
        },
    },
]
```

The complete, working settings for the default site are in `assets/default-site/settings_fragment.py`.

### MIDDLEWARE (order matters)
```python
MIDDLEWARE = [
    "cms.middleware.utils.ApphookReloadMiddleware",          # first: reloads stale URLconfs after apphook changes (cms convention; other positions untested)
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",              # after sessions
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware", # enforces X_FRAME_OPTIONS below
    "cms.middleware.user.CurrentUserMiddleware",              # cms middleware last
    "cms.middleware.page.CurrentPageMiddleware",
    "cms.middleware.toolbar.ToolbarMiddleware",
    "cms.middleware.language.LanguageCookieMiddleware",
]
```
The default site's `MIDDLEWARE` (`assets/default-site/settings_fragment.py`) includes `LocaleMiddleware` in the position shown above (after sessions, before common) and lists the cms middleware before `XFrameOptionsMiddleware`; both cms/clickjacking orders work. Verified 2026-10-01 on cms 5.1.3 / Django 5.2.17: `manage.py check` clean, four published pages return 200, logged-in users get the toolbar markup, responses carry `X-Frame-Options: SAMEORIGIN`. An earlier scratch project that listed only sessions, common, csrf, auth, messages and the four `cms.middleware.*` entries also booted and rendered, which is why this gap went unnoticed: it had no `SecurityMiddleware`, no clickjacking header, no locale handling and no apphook reload. Do not omit the stock Django entries.

The default site additionally puts `whitenoise.middleware.WhiteNoiseMiddleware` **directly after `SecurityMiddleware`** (WhiteNoise's documented position) and keeps `ApphookReloadMiddleware` first; the DEBUG-only debug toolbar is inserted at index 1, so with DEBUG on the order is apphook reload, toolbar, security, whitenoise, sessions, ...

### X-Frame-Options (for CMS toolbar)
```python
X_FRAME_OPTIONS = 'SAMEORIGIN'  # Allows CMS toolbar iframe to load
```

### Static files and site name

Required for any theme that ships a stylesheet. Without `STATICFILES_DIRS`, files in a project-level `static/` directory are not found; without a context processor, `{{ site_name }}` is undefined and renders empty (Django does not error).

```python
# settings.py
INSTALLED_APPS = [..., 'django.contrib.staticfiles', ...]   # included in a default startproject
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']      # project-level static/ (e.g. static/css/site.css)
STATIC_ROOT = BASE_DIR / 'staticfiles'        # collectstatic target; add to .gitignore
SITE_NAME = 'My Site'

TEMPLATES[0]['OPTIONS']['context_processors'] += ['myproject.context_processors.site']
```

```python
# myproject/context_processors.py
from django.conf import settings

def site(request):
    """Expose settings.SITE_NAME to every template as site_name."""
    return {"site_name": settings.SITE_NAME}
```

`runserver` serves `STATICFILES_DIRS` only when `DEBUG` is on. In production run `collectstatic` and serve `STATIC_ROOT` from the web server. Verified in a scratch project on cms 5.1.3 / Django 5.2.17: `/static/css/site.css` returned 200 as `text/css`.

### CMS Toolbar settings
```python
# Real django-cms 5.1.3 toolbar settings (verified in cms/utils/conf.py).
# All are optional; values shown are the defaults.
CMS_TOOLBAR_ANONYMOUS_ON = True        # toolbar login prompt visible to anonymous users
CMS_TOOLBAR_URL__ENABLE = "toolbar_on"
CMS_TOOLBAR_URL__DISABLE = "toolbar_off"
CMS_TOOLBAR_URL__PERSIST = "persist"
CMS_TOOLBAR_HIDE = False
```
The default site sets `CMS_TOOLBAR_ANONYMOUS_ON = False` so anonymous visitors never see the login prompt. `CMS_TOOLBAR_REQUIRE_SUPERUSER` and `ANONYMOUS_EDIT` do NOT exist in django-cms 5.1.3 (grepped in the installed package; do not set them, Django will silently ignore unknown settings). There is no setting to restrict the toolbar to superusers: who can edit is governed by Django and CMS permissions.

### DjangoCMS Versioning (built-in draft workflow)
```python
# In pyproject.toml or requirements.txt
dependencies = [
    "django-cms>=5.1,<5.2",
    "djangocms-versioning",
    "djangocms-alias",
    "djangocms-link",
    "djangocms-picture",
    "djangocms-text",
]
```
Versioning enables: unpublished drafts, version numbers, content approval workflows.

### admindocs (auto-generated admin documentation)
```python
# In INSTALLED_APPS
'django.contrib.admindocs',

# In urls.py: BEFORE path('admin/', ...), or the admin catch-all swallows it
path('admin/docs/', include('django.contrib.admindocs.urls')),
```
Requires `docutils`, which is **not** installed with Django: `pip install docutils` (without it the page shows "Please install docutils").

Prefix: Django's own documentation uses `admin/doc/`; this skill and the default site use `admin/docs/`. Both work as long as the prefix is placed before `admin/`; pick one and link to it consistently. The default site serves `/admin/docs/`. Verified with the Django test client (staff user gets 200); not opened in a browser.

### DjangoDebugToolbar (development only)
```python
# settings.py: enable ONLY when DEBUG is on (the default site adds an opt-out, see below)
if DEBUG:
    INSTALLED_APPS += ["debug_toolbar"]
    # index 1, NOT 0: ApphookReloadMiddleware must stay first in MIDDLEWARE
    MIDDLEWARE.insert(1, "debug_toolbar.middleware.DebugToolbarMiddleware")
    INTERNAL_IPS = ["127.0.0.1", "::1"]   # exact IPs only (no CIDR ranges)
```

```python
# urls.py
from django.conf import settings
if settings.DEBUG:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
```

The default site wraps this in one switch, `USE_DEBUG_TOOLBAR = DEBUG and DJANGO_DEBUG_TOOLBAR not in (0/false/no/off) and debug_toolbar is installed`, and uses it for the app, the middleware and the `/__debug__/` url, so they are always present or absent together (`DJANGO_DEBUG_TOOLBAR=0` leaves nothing referencing the missing app). The package lives in `requirements-dev.txt` only (the production image does not contain it; a DEBUG run without it just has no toolbar). The small green tab on the right edge of pages when `DJANGO_DEBUG=1` is **this debug toolbar's handle, not the CMS toolbar** (anonymous visitors get no CMS toolbar markup); it only exists when DEBUG is on, and it overlaps content in screenshots, which is why the generated `bin/verify.sh` starts its server with `DJANGO_DEBUG_TOOLBAR=0`.

Never install the toolbar unconditionally; gate apps, middleware, `INTERNAL_IPS` and the URL include on `DEBUG`. Verified: with `DJANGO_DEBUG` unset none of them are present; with it set all are, and `ApphookReloadMiddleware` is still first.

### Production hardening checklist
Run `python manage.py check --deploy` against your production settings; it must report nothing you have not consciously accepted. Verified 2026-10-01 on a scratch project: with the settings below, only W005, W019 and W021 remained.

```python
import os

DEBUG = False
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]        # 50+ chars, 5+ unique; never commit it
ALLOWED_HOSTS = ["example.org"]                       # never ["*"]
SECURE_SSL_REDIRECT = True                            # behind a TLS proxy also set SECURE_PROXY_SSL_HEADER
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000                        # start small (e.g. 3600) until you are sure
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```
Accepted trade-offs, not defects: `security.W019` (X_FRAME_OPTIONS is `SAMEORIGIN`, not `DENY`, because the CMS toolbar frames same-origin pages), `security.W005` (HSTS subdomains) and `security.W021` (HSTS preload) are per-site decisions. Also use a real database (PostgreSQL) rather than SQLite, and gate the debug toolbar on `DEBUG` (see above).

### Production vs development requirements (default site)
`requirements.txt` is production only; `requirements-dev.txt` is `-r requirements.txt` plus `django-debug-toolbar`. `docutils` is a **production** dependency here because `/admin/docs/` is enabled (move it to the dev file only if admindocs is removed from `INSTALLED_APPS` and `urls.py`). The Dockerfile has `dev` and `production` stages (production last, so it is the default) and the production image has no `debug_toolbar`; `docker-compose.dev.yml` is a standalone stack (own project name, volumes and port 8880, bound to 127.0.0.1).

### Docker / container settings (default site)
All of these are in `assets/default-site/settings_fragment.py` and `urls_fragment.py` and behave identically with or without the Docker files. Verified 2026-10-01 end to end (PostgreSQL 16, gunicorn, DEBUG off).

- **Database:** `DB_ENGINE=postgres` (also `postgresql`/`pgsql`) selects `django.db.backends.postgresql` from `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD` (plus `DB_CONN_MAX_AGE`, default 60); anything else keeps SQLite. Needs `psycopg[binary]` (bundles libpq; no apt packages).
- **Static:** `STORAGES['staticfiles']` is `whitenoise.storage.CompressedStaticFilesStorage` (non-manifest on purpose: a template referencing a missing file cannot break `collectstatic` or rendering). WhiteNoise warns `No directory at: .../staticfiles/` when `STATIC_ROOT` does not exist at startup; the settings create it (`STATIC_ROOT.mkdir(exist_ok=True)`) and the container entrypoint runs `mkdir -p staticfiles`. `collectstatic` runs at image build and again at container start.
- **Media with DEBUG off:** Django serves no uploads. `DJANGO_SERVE_MEDIA=1` (compose default) adds a `re_path(r'^media/(?P<path>.*)$', django.views.static.serve)` after the health/admin routes and before the CMS catch-all. Fine for a small site; behind nginx/caddy serve `/media/` there and set it to 0. With DEBUG on the usual `static()` route is used.
- **Health:** `GET /health/` (before `cms.urls`) runs `SELECT 1`: 200 `{"status": "ok"}` or 503. `never_cache`, GET/HEAD only.
- **Proxy / CSRF:** `DJANGO_CSRF_TRUSTED_ORIGINS` (comma separated, with scheme and port) feeds `CSRF_TRUSTED_ORIGINS`. `DJANGO_BEHIND_PROXY=1` sets `SECURE_PROXY_SSL_HEADER` and makes `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` and `LANGUAGE_COOKIE_SECURE` true (verified with curl and forwarded headers: csrftoken, sessionid and django_language all `Secure`). Optional: `DJANGO_HSTS_SECONDS`, `DJANGO_HSTS_INCLUDE_SUBDOMAINS`, `DJANGO_SSL_REDIRECT` (off by default; `SECURE_REDIRECT_EXEMPT = [r'^health/$']` keeps the healthcheck working). **Warning:** it trusts `X-Forwarded-Proto` from any client that can reach the port, so use it only behind a proxy that overwrites the header, never with `APP_BIND=0.0.0.0` exposed to untrusted clients.
- **Login throttling (django-axes 8.3.1):** `axes` in `INSTALLED_APPS`, `axes.backends.AxesStandaloneBackend` FIRST in `AUTHENTICATION_BACKENDS` (then `ModelBackend`), `axes.middleware.AxesMiddleware` LAST in `MIDDLEWARE` (axes' own docs; `manage.py check` warns axes.W002/W003 if either is missing). Settings used (each verified in `axes/conf.py` of the installed package): `AXES_ENABLED`, `AXES_FAILURE_LIMIT`, `AXES_COOLOFF_TIME` (timedelta; None = until reset), `AXES_LOCKOUT_PARAMETERS` (`[['username','ip_address']]`, or `['ip_address']`; axes.W006 requires `ip_address`), `AXES_RESET_ON_SUCCESS`, `AXES_NEVER_LOCKOUT_GET`, `AXES_CLIENT_IP_CALLABLE`, `AXES_LOCKOUT_CALLABLE` (429 page, `Retry-After`). The default handler is the database one: counters are shared by all gunicorn workers, work on SQLite and PostgreSQL and need no cache. Do not switch to the cache handler with `LocMemCache` (per process, it would give each worker its own counters; axes.W001 warns). Client IP: django-ipware is NOT installed (axes falls back to `REMOTE_ADDR` without it), so `<project>/security.py` `client_ip()` implements it: `REMOTE_ADDR` unless `DJANGO_BEHIND_PROXY=1`, then the `X-Forwarded-For` entry `DJANGO_PROXY_COUNT` hops from the right (the left side is client-controlled); malformed or missing falls back to `REMOTE_ADDR`. Env knobs: `DJANGO_LOGIN_FAILURE_LIMIT` (5; 0 disables), `DJANGO_LOGIN_COOLOFF_MINUTES` (60; 0 = until reset), `DJANGO_LOGIN_LOCKOUT_BY` (`ip_username` | `ip`), `DJANGO_PROXY_COUNT` (1). Operator unlock: `manage.py axes_reset` (also `axes_reset_ip`, `axes_reset_username`, `axes_reset_ip_username`, `axes_list_attempts`). Test client note: `client.login()` passes no request and axes raises `AxesBackendRequestParameterRequired`; use `force_login` (the generated tests do).
- **ALLOWED_HOSTS:** `localhost` and `127.0.0.1` are always appended (the container healthcheck sends `Host: 127.0.0.1`; without it a production `DJANGO_ALLOWED_HOSTS=example.org` made the container permanently unhealthy).
- **Cache:** django CMS keeps its menu/page/placeholder caches and their invalidation in the default cache. A per-process `LocMemCache` with several gunicorn workers served a stale menu after publishing (verified: 14/40 requests showed a freshly published child page in the nav). With PostgreSQL the default is `DatabaseCache` table `django_cache` (`createcachetable` runs in the entrypoint): 40/40. `DJANGO_CACHE=locmem|db` overrides; SQLite runs keep locmem. Under DEBUG the CMS page/placeholder/plugin caches are off (`CMS_PAGE_CACHE`, `CMS_PLACEHOLDER_CACHE`, `CMS_PLUGIN_CACHE`, all in `cms/utils/conf.py`) so edits show immediately; `DJANGO_CMS_CACHE=1` keeps them on.
- **filer private storage:** filer's default `MEDIA_ROOT/../smedia` is outside the volumes in a container. `FILER_STORAGES['private']` points inside `MEDIA_ROOT` (the full `main` and `thumbnails` entries including `ENGINE`, otherwise filer ignores them), and `urls.py` refuses `/media/filer_private*` with a 404.
- **Google Maps without a key:** with no `GOOGLE_MAPS_API_KEY`, `CMS_PLACEHOLDER_CONF[None]['excluded_plugins']` removes `GoogleMapPlugin`, `GoogleMapMarkerPlugin` and `GoogleMapRoutePlugin` from the editor plugin list (key `None` applies to every placeholder; `cms/plugin_pool.py`); an existing map renders a notice (`templates/djangocms_googlemap/default/map.html`), and `static/js/googlemap-guard.js` loads the plugin script only after Google's API has loaded (no `google is not defined`). `templates/djangocms_video/default/video_player.html` adds a text link under an embedded video; use an `/embed/` URL, a watch URL leaves the frame blank.
- **Seeding with versioning:** published content is never edited in place: `starter/seeding.py` `editable_content()` copies a published version to a draft, the seed fills it, `publish()` publishes once; pages are keyed on `PageUrl(slug, language)`. `manage.py seed --first-run-only` (used by `SEED_ON_START=1`) does nothing when the home page exists, so an editor's emptied placeholder is not refilled on restart; plain `seed` refills empty placeholders of the pages it owns.
- **Backup and restore:** `bin/docker-backup.sh` writes `db.sql` and `media.tar.gz`. Restore order matters: start ONLY `db`, load the dump with `psql -v ON_ERROR_STOP=1`, then start the app (restoring into a database the app already migrated fails with hundreds of "already exists" errors); media is untarred into `/app/media`.
- **Images:** pinned as `name:tag@sha256:<index digest>`; `bin/pin-images.sh --check` compares with the registry (HTTP API only).
- **gunicorn:** run it as a non-root user with `--no-control-socket` (the control socket needs a writable home directory and otherwise errors at startup). `--access-logfile -` sends access logs to the container log.
