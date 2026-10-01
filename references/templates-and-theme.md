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
