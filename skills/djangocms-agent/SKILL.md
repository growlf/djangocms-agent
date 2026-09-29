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
  version: "0.3.0"
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
every change by taking a screenshot and analyzing visible content.

### Before making changes:
```bash
# Start the dev server if not running
uv run python manage.py runserver 0.0.0.0:8000 &

# Take baseline screenshot
uv run python scripts/visual_check.py http://localhost:8000/home/ /tmp/before.png
```

### After making changes:
```bash
# Take validation screenshot
uv run python scripts/visual_check.py http://localhost:8000/home/ /tmp/after.png

# Report findings:
# - What changed visually
# - Any errors detected (404, template errors, server errors)
# - What's missing (empty placeholders, missing menu)
# - What's working (content rendered, template loaded)
```

### Visual check script locations:
- `scripts/visual_check.py` — takes screenshots and reports visible content
- Output saved to `/tmp/cms-check.png` (or specify path)
- Reports HTTP status, visible text, and common error patterns

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
CMS_TOOLBAR_ANONYMOUS_EDIT = False  # Only show toolbar for logged-in users
CMS_TOOLBAR_REQUIRE_SUPERUSER = True  # Require superuser for toolbar
CMS_TOOLBAR_URL__EDIT_ON = 'edit'  # ?edit parameter to enable edit mode
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
    "djangocms-text-ckeditor",
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
# In pyproject.toml
dependencies = ["django-debug-toolbar"]

# In INSTALLED_APPS (at top!)
INSTALLED_APPS = [
    'debug_toolbar',  # Must be before other apps
    ...
]

# In MIDDLEWARE (at top!)
MIDDLEWARE = [
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    ...
]

# In urls.py
import sys
if 'debug_toolbar' in INSTALLED_APPS:
    import socket
    hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS = [ip[:-1] + '1' for ip in ips] + ['127.0.0.1', '10.0.2.2']
    urlpatterns += [
        path('__debug__/', include('debug_toolbar.urls')),
    ]
```
Toolbar only shows for INTERNAL_IPS. Safe for production.

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
    # Core (always include)
    "djangocms-alias",      # Reusable content fragments
    "djangocms-link",       # Links with rich options
    "djangocms-picture",    # Image plugin
    "djangocms-text-ckeditor",  # WYSIWYG text editor
    
    # Media & content
    "djangocms-video",      # Video embedding
    "djangocms-file",       # File downloads
    "djangocms-style",      # Text styling classes
    
    # UI components
    "djangocms-bootstrap5", # Bootstrap grid/components
    "djangocms-social",     # Social media buttons
    
    # Advanced (optional)
    "djangocms-googlemap",  # Embedded maps
    "djangocms-form",       # Contact forms
]
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

## When to Use
### Root URL redirect (avoid admin redirect)
```python
# In urls.py
def root_redirect(request):
    return redirect('/home/')

urlpatterns = [
    path('', root_redirect, name='root'),
    path('admin/', admin.site.urls),
    path('', include('cms.urls')),
]
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
    # Core (always include)
    "djangocms-alias",      # Reusable content fragments
    "djangocms-link",       # Links with rich options
    "djangocms-picture",    # Image plugin
    "djangocms-text-ckeditor",  # WYSIWYG text editor
    
    # Media & content
    "djangocms-video",      # Video embedding
    "djangocms-file",       # File downloads
    "djangocms-style",      # Text styling classes
    
    # UI components
    "djangocms-bootstrap5", # Bootstrap grid/components
    "djangocms-social",     # Social media buttons
    
    # Advanced (optional)
    "djangocms-googlemap",  # Embedded maps
    "djangocms-form",       # Contact forms
]
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
4. **Django migrations** → follow `django-expert` migrations + `djangocms-migration` for CMS-specific patterns
5. **Django testing** → follow `django-expert` testing guidance

## Skills

| Skill | Trigger Files |
|-------|---------------|
| `djangocms-architecture` | `cms/urls.py`, `CMS_TEMPLATES`, `cms.py` |
| `djangocms-pages` | `Page`, `PageUrl`, `PageContent`, `create_page` |
| `djangocms-placeholders` | `Placeholder`, `render_block`, `{% cms_placeholder %}` |
| `djangocms-templates` | CMS templates, `{% load cms_tags %}`, `{% show_menu %}` |
| `djangocms-admin` | `cms.admin.*`, `PageAdmin`, plugin admin files |
| `djangocms-plugins` | Custom plugin files, `CMSConfig`, apphooks |
| `djangocms-middleware` | `MIDDLEWARE`, CMS settings, CMS configuration |
| `djangocms-migration` | CMS migrations, `RunPython` on CMS models |

## CMS Gotchas (from TheNetYeti)

These are captured from production experience with Django + DjangoCMS integration:

- **`create_page` requires `language="en-us"`** — no `published=` kwarg (uses `CMS_DEFAULT_INTENT`)
- **CMS page lookup** — slugs live in `PageUrl`: `PageUrl.objects.get(slug=slug).page`
- **Re-pointing page templates** — use `PageContent.objects.filter(page=page, language="en-us").first().template`
- **`{% render_block %}`** — cannot live inside a `{% block %}` (swallows following `{% endblock %}`)
- **`{% show_menu %}`** — requires `{% load menu_tags %}` (not loaded by `cms_tags` alone)
- **`{% %}` inside `{# #}` comments** — tokenizes/parse-fails; keep DTL comments free of `{% %}`

## CMS 5.x Notes

- **`CMS_CONFIRM_VERSION4` removed** — this setting was only needed for the CMS 4.x migration path from 3.x. Not needed in 5.x.
- **`CMS_DEFAULT_INTENT`** — still controls the default publish state for `create_page` (default: `"draft"`)
- **sekizai** — still requires `{% render_block "css" %}` (sekizai 4.x+ syntax); `{% slot %}` is not used
- **menus** — the `menus.context_processors.menus` processor does not exist; use `{% show_menu %}` with `{% load menu_tags %}`

## References

- [CMS API Cheatsheet](references/cms-api-cheatsheet.md)
- [CMS Settings Reference](references/cms-settings-reference.md)
- [CMS Commands Reference](references/cms-commands-cheatsheet.md)
