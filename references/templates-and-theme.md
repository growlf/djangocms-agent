### Default theme: Bootstrap 5.3 (verified on cms 5.1.3 / Django 5.2.17)

The default site lives in `assets/default-site/` (reachable from an installed skill as `assets/default-site/`). It is the single copy; there are no duplicated template or CSS files in `references/`. Read `assets/default-site/README.md` for the file map, placeholders and seed rules.

| Asset | Copy to | Purpose |
|---|---|---|
| `templates/base.html` | `templates/base.html` | Shell: Bootstrap navbar with hamburger (`navbar-expand-lg`, collapse), footer, skip link, `{% render_block %}` for css/js |
| `templates/landing.html` | `templates/landing.html` | Hero, three feature columns, content, call-to-action band (slots `hero`, `feature_1..3`, `content`, `cta`) |
| `templates/standard.html` | `templates/standard.html` | `content` (`col-lg-8`) plus a right `sidebar` (`col-lg-4`) that stacks on small screens |
| `templates/menu/menu.html`, `menu/footer_menu.html` | `templates/menu/` | Header menu: dropdown for level 0 parents, deeper levels flattened and indented; footer list |
| `static/css/site.css` | `static/css/site.css` | `--site-*` custom properties bridged onto Bootstrap's `--bs-*`, spacing for text content, focus, print |
| `static/js/theme.js` | `static/js/theme.js` | Sets `data-bs-theme` from `prefers-color-scheme` (light/dark), loaded in `<head>` to avoid a flash |
| `static/vendor/bootstrap/` | same | Bootstrap 5.3.3 CSS + bundle JS, vendored (no CDN, works on a LAN) with its MIT `LICENSE` |

Also required (settings in `assets/default-site/settings_fragment.py`, explained in `project-setup.md`, "Static files and site name"): `STATICFILES_DIRS`, `STATIC_ROOT`, a `SITE_NAME` setting and the context processor that exposes it as `site_name`. Nothing defines `site_name` for you; without it the title, brand and footer render empty.

Page templates and slots, kept in sync with `CMS_PLACEHOLDER_CONF`:

```python
CMS_TEMPLATES = [
    ('landing.html', 'Landing page (hero)'),
    ('standard.html', 'Standard page (right sidebar)'),
]
```
Do not add `'plugins'` allow-lists unless you mean to: with none, every installed plugin is available in every slot.

Rules these templates follow (and any replacement must too):
- `{% render_block "css" %}` and `{% render_block "js" %}` stay outside any `{% block %}`.
- `{% block main %}` wraps the placeholder(s), so apphook and other templates can `{% extends "base.html" %}` and override only `main`.
- Only the standard template renders a sidebar. Keep placeholder slot names in sync between templates and `CMS_PLACEHOLDER_CONF`.
- `{% show_menu %}` emits bare `<li>` items, so `base.html` wraps it in `<ul class="navbar-nav menu">`.
- Do not put `{% %}` tags inside `{# #}` comments.
- Bootstrap JS is loaded after `{% render_block "js" %}`; dropdowns and the hamburger need `data-bs-toggle` attributes, which djangocms-text strips. Put such markup in a template or the trusted Raw HTML block (`starter.HtmlBlock`), never in a text plugin.

### Menu template

Use `{% load menu_tags %}` then `{% show_menu 0 100 100 100 "menu/menu.html" %}`. It only lists pages created with `in_navigation=True` (`create_page` defaults to `False`, which gives an empty menu). It works with or without `cms.context_processors.cms_settings`.

The stock `menu/menu.html` emits bare `<li class="child selected ...">` with no wrapper and an unclassed nested `<ul>`, which is why the default site overrides it. The recursive `{% show_menu from_level to_level extra_inactive extra_active template "" "" child %}` call renders each submenu. Level 3 and deeper are deliberately flat items inside the level-0 dropdown (no nested dropdowns, so touch and keyboard just work).

A hand-rolled loop over `request.current_page.get_root_nodes` also renders, but it ignores `in_navigation` and has no submenu or active-trail logic; prefer the template above.

### Verification checklist

Ticked items were actually run against a scratch project built from `assets/default-site` (cms 5.1.3), with `scripts/visual_check.py` on `/`, `/about/` and `/style-and-capabilities/`:
- [x] `scripts/visual_check.py` desktop and `--mobile`: RESULT: PASS on all three pages
- [x] Hamburger click test at a 390px viewport (Playwright): menu hidden before, visible after clicking the toggler
- [x] Dropdown markup and nested-menu behaviour (template tests with a three-level tree)
- [x] Dark mode: readable in screenshots during the original build (`data-bs-theme` set by `theme.js`); not re-checked in this port and not by a contrast tool
- [x] `manage.py test starter`: 20 tests pass
- [ ] Logged-in CMS toolbar in a browser (only covered by test client markup checks)
- [ ] `/admin/docs/` in a browser (only the test client checks it returns 200)
- [ ] Numeric contrast check (no contrast tool was run)
- [ ] Dropdown opening by mouse/keyboard in a real browser (markup only; the hamburger was clicked)

Untick or add items rather than assuming when you change the theme.

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
