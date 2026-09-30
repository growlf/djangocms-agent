---
name: djangocms-agent
description: >-
  DjangoCMS specialist agent for django-cms 5.x. Handles page trees,
  placeholders, templates, content plugins, admin customization, middleware,
  and migrations. REQUIRES visual validation after every change.
  Includes django-ai-plugins and agentic-django as Django foundation dependencies.
  Use for any DjangoCMS work: creating pages with placeholders, building custom
  CMS plugins, configuring CMS settings, writing CMS migrations, and customizing
  the CMS admin.
  
  This agent credits and builds on:
  - vintasoftware/django-ai-plugins (MIT) for multi-host agent structure
  - MohamedMandour10/agentic-django for Django architecture patterns
  
  DO NOT USE FOR: general Django work not involving CMS — use the
  django-expert skill from vintasoftware/django-ai-plugins for that.
  DO NOT USE FOR: Azure OpenAI, infrastructure, security — use the
  appropriate domain-specific agent for those.
license: MIT
metadata:
  author: growlf
  version: "0.5.0"
  compatibility: claude-code, opencode, codex, cursor
  stack:
    python: "3.12|3.13"
    django: "5.2 LTS"
    django-cms: "5.1.3"
---

# DjangoCMS Agent

> **DjangoCMS specialist** — handles the entire django-cms 5.x stack.
>
> **Credit:** Built on patterns from [vintasoftware/django-ai-plugins](https://github.com/vintasoftware/django-ai-plugins) (MIT) and [MohamedMandour10/agentic-django](https://github.com/MohamedMandour10/agentic-django).

## VISUAL VALIDATION (MANDATORY)

**Never make CMS changes without visual confirmation.** The agent must validate
every change by running `scripts/visual_check.py` and reporting the RESULT line.

One-time setup: `pip install playwright && playwright install chromium`.

```bash
# Desktop (1280×800) — default screenshot path /tmp/cms-check.png
python scripts/visual_check.py http://localhost:8000/

# Mobile viewport (390×844)
python scripts/visual_check.py http://localhost:8000/ --mobile

# Require specific text on the page
python scripts/visual_check.py http://localhost:8000/ --expect-text "Welcome"

# With login (password read from environment variable)
python scripts/visual_check.py http://localhost:8000/ --login admin:DJANGO_PASS

# Custom screenshot path
python scripts/visual_check.py http://localhost:8000/ --out /tmp/verify.png
```

Exit codes: 0 = no issues, 1 = issues found, 2 = script/browser error.
Output includes URL, final URL, HTTP status, page title, first 300 chars of visible text,
then any ISSUE lines, ending with `RESULT: PASS` or `RESULT: FAIL (N issues)`.
If you cannot view images, rely on the printed text and exit code; do not claim visual confirmation.

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
Docs available at `/admin/docs/`. Requires `docutils` (included with Django).

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

### Default CMS template (generic theme with dynamic menu)
```python
# In settings.py
CMS_TEMPLATES = [
    ('default', 'Default'),
]

CMS_PLACEHOLDER_CONF = {
    'content': {
        'plugins': ['TextPlugin', 'PicturePlugin', 'LinkPlugin', 'AliasPlugin'],
        'name': 'Content',
        'extra_context': {'width': False},
    },
    'sidebar': {
        'plugins': ['LinkPlugin', 'PicturePlugin', 'AliasPlugin'],
        'name': 'Sidebar',
        'extra_context': {'width': False},
    },
}
```


### Default Theme (professional, mobile-friendly)
Create `templates/default.html` with:
- Mobile-first responsive CSS (use CSS custom properties for theming)
- Proper typography (system font stack: -apple-system, BlinkMacSystemFont, 'Segoe UI', etc.)
- CSS grid/flexbox layout with max-width containers
- Dark/light mode support (prefers-color-scheme)
- Accessible markup (ARIA labels, semantic HTML5 elements)
- Site navigation menu with dropdown support
- Footer with standard links
- Placeholder regions: `{% placeholder "content" %}` and `{% placeholder "sidebar" %}`
- CMS toolbar: `{% cms_toolbar %}`
- Sekizai blocks: `{% render_block "css" %}` and `{% render_block "js" %}`

See `references/default-theme.html` for a production-ready template.

### Recommended CMS Plugins (stable, maintained)
```python
dependencies = [
    # Proven on cms 5.1.3 (TheNetYeti): djangocms-text, djangocms-link, djangocms-snippet, djangocms-versioning, django-filer
    # Core (always include)
    "djangocms-alias",      # Reusable content fragments
    "djangocms-link",       # Links with rich options
    "djangocms-picture",    # Image plugin
    "djangocms-text",       # WYSIWYG text editor
    
    # Media & content
    "djangocms-video",      # Video embedding  # untested on cms 5.1.3
    "djangocms-file",       # File downloads
    "djangocms-style",      # Text styling classes
    
    # UI components
    "djangocms-bootstrap5", # Bootstrap grid/components  # untested on cms 5.1.3
    "djangocms-social",     # Social media buttons  # untested on cms 5.1.3
    
    # Advanced (optional)
    "djangocms-googlemap",  # Embedded maps  # untested on cms 5.1.3
    "djangocms-form",       # Contact forms  # untested on cms 5.1.3
]

# Transitive pins the site needed:
# djangocms-attributes-field, django-filer, django-polymorphic, django-mptt,
# easy-thumbnails, pillow, lxml, nh3, django-fsm-2
```

### Default CSS (professional styling)
Create `static/css/netyeti.css` with:
- CSS custom properties for colors, spacing, typography
- Mobile-first media queries
- Print styles
- Focus/accessible states
- Smooth scroll behavior
- Professional color palette (not default browser colors)

See `references/default.css` for a complete production stylesheet.


### Project Defaults (partially verified — see CHANGELOG)

Starting point; items not marked verified in CHANGELOG are unproven:

```python
# settings.py - starting point (plugin apps below other than text/link/versioning/filer are untested on cms 5.1.3)
INSTALLED_APPS = [
    'cms', 'menus', 'sekizai', 'treebeard',  # CMS core
    'djangocms_admin_style',  # Admin styling
    'mptt', 'easy_thumbnails', 'filer',  # Media
    'djangocms_alias', 'djangocms_link', 'djangocms_picture',
    'djangocms_text', 'djangocms_video', 'djangocms_file',
    'djangocms_style', 'djangocms_bootstrap5',
    'djangocms_versioning',  # Draft workflow
]

# TEMPLATES - keep the app_directories loader so plugin templates resolve
TEMPLATES = [{
    'OPTIONS': {
        'loaders': [
            'django.template.loaders.filesystem.Loader',
            'django.template.loaders.app_directories.Loader',
        ],
        'context_processors': [
            'sekizai.context_processors.sekizai',
            'cms.context_processors.cms_settings',
        ],
    },
}]

# CMS toolbar requires SAMEORIGIN
X_FRAME_OPTIONS = 'SAMEORIGIN'
```

### Template Structure (unverified — render-test before relying on it)

Note: `menu/hamburger.html` and `{{ site_name }}` are not shipped/defined by this repo; supply your own or replace them.

```html
{% load cms_tags sekizai_tags menu_tags static %}
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% page_attribute "page_title" %} | {{ site_name }}</title>
    <link rel="stylesheet" href="{% static 'css/netyeti.css' %}">
    {% render_block "css" %}
</head>
<body class="cms cms-home">
    {% cms_toolbar %}
    <header class="site-header">
        {% include "menu/hamburger.html" %}
    </header>
    <main class="site-main">
        <div class="content-sidebar">
            <div class="content">{% placeholder "content" %}</div>
            <aside class="sidebar">{% placeholder "sidebar" %}</aside>
        </div>
    </main>
    <footer class="site-footer">
        <p>&copy; {% now "Y" %} {{ site_name }}</p>
    </footer>
    {% render_block "js" %}
</body>
</html>
```

### Menu Template (UNVERIFIED — render-test before relying on it)

Preferred approach: `{% load menu_tags %}` then `{% show_menu 0 100 100 100 %}`. The hand-rolled loop below uses `request.current_page.get_root_nodes`, which has not been verified to exist.

```html
{% load cms_tags %}
<nav class="site-nav">
    <button class="nav-toggle" aria-label="Toggle navigation">
        <span class="hamburger-icon"></span>
    </button>
    <ul class="nav-menu">
        {% for page in request.current_page.get_root_nodes %}
        <li class="nav-item{% if page == request.current_page %} active{% endif %}">
            <a href="{{ page.get_absolute_url }}">{{ page.get_menu_title }}</a>
        </li>
        {% empty %}
        <li class="nav-item"><a href="/">Home</a></li>
        {% endfor %}
    </ul>
</nav>
```

### Mobile Verification Checklist (run these checks; none are proven yet)

- [ ] Hamburger button visible on mobile (< 768px)
- [ ] Menu opens on click
- [ ] Menu items visible and clickable
- [ ] Menu closes when tapping outside
- [ ] Desktop view shows horizontal menu
- [ ] CSS grid/flexbox responsive layout
- [ ] Dark/light mode support


### Root URL redirect (only when the CMS home page is NOT served at `/`)
```python
# In urls.py
HOME_URL = '/home/'  # URL of your CMS home page; must NOT be '/' (that would redirect to itself)

def root_redirect(request):
    return redirect(HOME_URL)

urlpatterns = [
    path('', root_redirect, name='root'),
    path('admin/', admin.site.urls),
    path('', include('cms.urls')),
]
```


## When to Use

Invoke this agent when working with any DjangoCMS-related code:

- Creating/editing CMS pages, page trees, slugs
- Configuring `CMS_TEMPLATES`, placeholders, sekizai
- Writing custom CMS content plugins or apphooks
- Customizing the CMS admin (`PageAdmin`, plugin admin)
- Writing CMS migrations or data migrations
- Configuring CMS middleware, settings
- CMS template development (`{% load cms_tags %}`, `{% show_menu %}`)
- Debugging CMS page rendering, nav, or placeholder issues

## When NOT to Use

- **General Django work** (models, views, serializers, DRF) → use `django-expert` from [vintasoftware/django-ai-plugins](https://github.com/vintasoftware/django-ai-plugins)
- **Django architecture patterns** (service layer, selectors) → use `agentic-django` from [MohamedMandour10/agentic-django](https://github.com/MohamedMandour10/agentic-django)
- **Azure OpenAI / Foundry** → use `microsoft-foundry`
- **Security auditing** → use `secure-code-auditor`
- **Infrastructure / DevOps** → use `OpsKit`

## Dependency: Django Foundation

When working on Django code that touches both CMS and non-CMS areas (models,
views, admin, migrations), follow the relevant skill from the Django foundation
agents in addition to CMS-specific guidance:

1. **Django models/ORM** → follow `django-expert` models guidance
2. **Django views/DRF** → follow `django-expert` views/API guidance
3. **Django admin** → follow `django-expert` admin guidance (non-CMS parts)
4. **Django migrations** → follow `django-expert` migrations; for CMS models use `PageUrl`/`PageContent` (see CMS Gotchas) in `RunPython`.
5. **Django testing** → follow `django-expert` testing guidance

## Scope

This single skill covers pages, placeholders, templates, plugins, admin, middleware and migrations. Detailed material is in the files under references/.

## CMS Gotchas (from TheNetYeti)

These are captured from production experience with Django + DjangoCMS integration:

- **`create_page` requires `language="en-us"`** — no `published=` kwarg
- **CMS page lookup** — slugs live in `PageUrl`: `PageUrl.objects.get(slug=slug).page`
- **Re-pointing page templates** — use `PageContent.objects.filter(page=page, language="en-us").first().template`
- **`{% render_block %}`** — cannot live inside a `{% block %}` (swallows following `{% endblock %}`)
- **`{% show_menu %}`** — requires `{% load menu_tags %}` and the context processor `cms.context_processors.cms_settings` (it provides `cms_menu_renderer`). There is no `menus.context_processors.menus`. If `show_menu` renders nothing or errors, first check that `cms_settings` is in `TEMPLATES[0]["OPTIONS"]["context_processors"]`.
- **`{% %}` inside `{# #}` comments** — tokenizes/parse-fails; keep DTL comments free of `{% %}`

## CMS 5.x Notes

- **`CMS_CONFIRM_VERSION4` removed** — this setting was only needed for the CMS 4.x migration path from 3.x. Not needed in 5.x.
- **sekizai** — still requires `{% render_block "css" %}`; `{% slot %}` is not used
- **menus** — see show_menu gotcha above

## References

- [CMS API Cheatsheet](references/cms-api-cheatsheet.md)
- [CMS Settings Reference](references/cms-settings-reference.md)
- [CMS Commands Reference](references/cms-commands-cheatsheet.md)
