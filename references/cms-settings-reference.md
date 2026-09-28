## CMS Settings Reference

### Required Settings

```python
CMS_CONFIRM_VERSION4 = True  # MANDATORY for CMS 4.x

CMS_TEMPLATES = [
    ("template_name.html", "Display Name"),
]

SITE_ID = 1  # Required for django.contrib.sites

CMS_LANGUAGES = { ... }  # Required for language handling
```

### INSTALLED_APPS

```python
INSTALLED_APPS = [
    # Django
    "django.contrib.sites",  # Required
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.admin",
    "django.contrib.staticfiles",
    "django.contrib.messages",
    
    # django-cms
    "cms",              # Required
    "menus",            # Required (PLURAL, NOT "menu")
    "treebeard",        # Required
    "sekizai",          # Required
    
    # Your apps
    "netyeti_theme_dtl",
    "thenetyeti",
]

MIDDLEWARE = [
    # ... standard Django middleware ...
    "django.middleware.locale.LocaleMiddleware",  # Required
    "cms.middleware.user.CurrentUserMiddleware",  # Optional
    "cms.middleware.page.CurrentPageMiddleware",  # Optional
    "cms.middleware.toolbar.ToolbarMiddleware",   # Optional
    "cms.middleware.language.LanguageCookieMiddleware",  # Optional
]
```

### Template Context Processors

```python
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.i18n",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "sekizai.context_processors.sekizai",  # Required for sekizai 4.x
                # "menus.context_processors.menus",  # May not be available
            ],
        },
    },
]
```

### Key Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `CMS_CONFIRM_VERSION4` | — | **Mandatory** — prevents running on CMS 3.x |
| `CMS_TEMPLATES` | — | List of (template_path, display_name) tuples |
| `CMS_PLACEHOLDER_CONF` | — | Per-placeholder configuration |
| `CMS_PERMISSION` | `False` | Enable page-level permissions |
| `CMS_SEO_FIELDS` | `True` | Add SEO meta fields to page admin |
| `CMS_LANGUAGES` | — | Language configuration (required) |
| `CMS_TOOLBAR_URL__PASTE` | `paste` | URL param for toolbar paste action |
| `CMS_NAVIGATION_EXTENDERS` | `[]` | Custom menu rendering hooks |
| `CMS_DEFAULT_INTENT` | `"draft"` | Default publish state for new pages |

### sekizai Integration

```python
# sekizai 4.x uses render_block, NOT slot
# In templates:
#   {% render_block "css" %}
#   {% render_block "js" %}

# Context processor required:
#   sekizai.context_processors.sekizai
```
