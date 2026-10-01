### Default theme (verified on cms 5.1.3 / Django 5.2.17)

A small, dependency-free theme: two CMS templates, a styled nested menu and one stylesheet. It was built and checked in a scratch project ("testsite"): all pages passed `scripts/visual_check.py` on desktop and `--mobile`, and the template tests passed. Files in `references/`:

| Reference file | Copy to | Purpose |
|---|---|---|
| `default-theme.html` | `templates/base.html` | Base chrome (header, nav, footer) with the `content` placeholder; single-column |
| `default-theme-two-column.html` | `templates/two_column.html` | Extends base; adds a `sidebar` placeholder and a responsive 3fr/1fr grid |
| `default-menu.html` | `templates/menu/menu.html` | Menu template for `{% show_menu 0 100 100 100 "menu/menu.html" %}` |
| `default.css` | `static/css/site.css` | Tokens, layout, menu, dark mode, print |

Also required (see `project-setup.md`, "Static files and site name"): `STATICFILES_DIRS`, `STATIC_ROOT`, a `SITE_NAME` setting and a context processor that exposes it as `site_name`. Nothing defines `site_name` for you; without it the title, logo and footer render empty.

```python
CMS_TEMPLATES = [
    ('base.html', 'Standard'),
    ('two_column.html', 'Two column'),
]

CMS_PLACEHOLDER_CONF = {
    'content': {'name': 'Content', 'plugins': ['TextPlugin', 'LinkPlugin', 'AliasPlugin']},
    'sidebar': {'name': 'Sidebar', 'plugins': ['TextPlugin', 'LinkPlugin', 'AliasPlugin']},
}
```

What the theme does (all in `default.css`):
- CSS custom properties (`--site-*`), mobile-first layout, system font stack.
- Light and dark colour schemes via `prefers-color-scheme` (dark tokens override the light ones; `color-scheme: light dark` is set).
- `:focus-visible` outlines, a skip link, underlined links, reduced-motion handling, print styles.
- Spacing is restored for text-plugin content (headings, paragraphs, lists, tables, code).
- Menu: current page `.selected`, ancestors `.ancestor`, items with children `.has-children`. On desktop (>= 768px) nested levels open as dropdowns on hover or keyboard focus and the third level opens leftwards so it stays on screen; below that, nested levels show inline and indented. There is no hamburger toggle.

Rules these templates follow (and that any replacement must too):
- `{% render_block "css" %}` and `{% render_block "js" %}` stay outside any `{% block %}`.
- `{% block main %}` wraps the placeholder(s), so apphook and other templates can `{% extends "base.html" %}` and override only `main`.
- Only the two-column template renders a sidebar. Keep placeholder slot names in sync between templates and `CMS_PLACEHOLDER_CONF`.
- `{% show_menu %}` emits bare `<li>` items, so the template wraps it in `<ul class="menu">`.
- Do not put `{% %}` tags inside `{# #}` comments.

### Unverified items
- Bootstrap compatibility: this theme is plain CSS, not Bootstrap. `djangocms_bootstrap5` is only listed as an optional plugin app.
- Contrast was judged by eye; no numeric contrast tool was run (link `#1d4ed8` on white and `#4b5563` muted text are expected to be above AA, not measured).


### Project Defaults (partially verified — see CHANGELOG)

Starting point; items not marked verified in CHANGELOG are unproven:

```python
# settings.py - starting point (plugin apps below other than text/link/versioning/filer are untested on cms 5.1.3)
INSTALLED_APPS = [
    'django.contrib.sites',  # REQUIRED by cms (also set SITE_ID = 1) — startup fails without it
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

### Menu template

Use `{% load menu_tags %}` then `{% show_menu 0 100 100 100 "menu/menu.html" %}`. It only lists pages created with `in_navigation=True` (`create_page` defaults to `False`, which gives an empty menu). It works with or without `cms.context_processors.cms_settings`.

`references/default-menu.html` is the template used by the theme. The stock `menu/menu.html` emits bare `<li class="child selected ...">` with no wrapper and an unclassed nested `<ul>`, which is why the theme overrides it and wraps the call in `<ul class="menu">`. The recursive `{% show_menu from_level to_level extra_inactive extra_active template "" "" child %}` call renders each submenu.

A hand-rolled loop over `request.current_page.get_root_nodes` also renders, but it ignores `in_navigation` and has no submenu or active-trail logic; prefer the template above.

### Verification checklist

Run against the theme in a scratch project (cms 5.1.3), using `scripts/visual_check.py` on `/`, a nested page, the two-column page and an apphook page, each with and without `--mobile`:
- [x] Pages render with the stylesheet (`/static/css/site.css` returns 200 as `text/css`)
- [x] Desktop view shows a horizontal menu; current page is marked (`aria-current="page"`)
- [x] Nested menu levels open as dropdowns on desktop and show inline on mobile
- [x] Two-column layout stacks on mobile
- [x] Dark scheme renders readably (checked in screenshots, not by contrast tool)
- [ ] Numeric contrast check
- [ ] Hamburger/collapse toggle (not implemented)


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
