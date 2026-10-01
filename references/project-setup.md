## PROJECT SETUP (DEFAULT SETTINGS)

When creating a new DjangoCMS project, always include these settings in `settings.py`:

### TEMPLATES (with app_directories loader)
```python
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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
                'django.template.loaders.app_directories.Loader',  # REQUIRED for CMS plugins
            ],
        },
    },
]
```

### X-Frame-Options (for CMS toolbar)
```python
X_FRAME_OPTIONS = 'SAMEORIGIN'  # Allows CMS toolbar iframe to load
```

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

# In urls.py
path('admin/docs/', include('django.contrib.admindocs.urls')),
```
Docs available at `/admin/docs/`. Requires `docutils`, which is **not** installed with Django: `pip install docutils` (without it `/admin/docs/` shows "Please install docutils").

### DjangoDebugToolbar (development only)
```python
# settings.py — enable ONLY when DEBUG is on
if DEBUG:
    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
    INTERNAL_IPS = ["127.0.0.1", "::1"]   # exact IPs only (no CIDR ranges)
```

```python
# urls.py

from django.conf import settings
if settings.DEBUG:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
```

Never install the toolbar unconditionally; gate it on DEBUG.
