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
The default site's `MIDDLEWARE` (`assets/default-site/settings_fragment.py`) lists the cms middleware before `XFrameOptionsMiddleware` and omits `LocaleMiddleware` (single-language site); both orders work. Verified 2026-10-01 on cms 5.1.3 / Django 5.2.17: `manage.py check` clean, four published pages return 200, logged-in users get the toolbar markup, responses carry `X-Frame-Options: SAMEORIGIN`. An earlier scratch project that listed only sessions, common, csrf, auth, messages and the four `cms.middleware.*` entries also booted and rendered, which is why this gap went unnoticed: it had no `SecurityMiddleware`, no clickjacking header, no locale handling and no apphook reload. Do not omit the stock Django entries.

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
# settings.py: enable ONLY when DEBUG is on
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
