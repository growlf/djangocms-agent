## CMS API Cheatsheet

### Page Operations

```python
from cms.api import create_page, add_plugin
from cms.models.pagemodel import Page
from cms.models.titlemodels import PageUrl, PageContent
from django.contrib.sites.models import Site

# Create a page
page = create_page(
    title="My Page",
    template="page.html",
    language="en-us",  # Required; must be a code in LANGUAGES/CMS_LANGUAGES
    in_navigation=True,
)

# Access by slug
page_url = PageUrl.objects.get(slug="my-page")
page = page_url.page

# Language-specific content
page_content = PageContent.objects.filter(
    page=page, language="en-us"
).first()

# Change template assignment
page_content.template = "other_template.html"
page_content.save()
```

### Placeholder Operations

```python
from cms.models import Placeholder

# Get or create a placeholder
placeholder = Placeholder.objects.get_or_create(
    slot="body"  # Must match {% placeholder "body" %} in template
)[0]

# Add a plugin to a placeholder
plugin = add_plugin(
    placeholder,
    "TextPlugin",  # Plugin type
    "en-us",
    body="Hello world"
)
```

### CMS Settings

```python
# settings.py

CMS_TEMPLATES = [
    ("page.html", "Default Page"),
    ("landing.html", "Landing Page"),
]

CMS_PLACEHOLDER_CONF = {
    "body": {
        "plugins": ["TextPlugin", "LinkPlugin", "PicturePlugin"],
        "default_width": False,
    },
}

CMS_PERMISSION = False  # Enable if you want page-level permissions
CMS_LANGUAGES = {
    1: [
        {"code": "en-us", "name": "English", "fallbacks": []},
    ],
    "default": {
        "fallbacks": ["en-us"],
        "restrict_to_current_language": False,
    },
}
```

### CMS Commands

```bash
# Create a superuser
python manage.py createsuperuser

# Create CMS pages programmatically
python manage.py shell -c "
from cms.api import create_page
from django.contrib.sites.models import Site
site = Site.objects.get_current()
create_page('Home', 'page.html', 'en-us', site=site)
"

# Check CMS status
python manage.py cms check

# Clear CMS cache
python manage.py clear_cms_cache
```

### Apphooks

Verified on cms 5.1.3 / Django 5.2.17 (testsite project, 2026-09-30).

```python
# myapp/cms_apps.py
from cms.app_base import CMSApp
from cms.apphook_pool import apphook_pool

@apphook_pool.register
class MyApp(CMSApp):
    name = "My app"
    app_name = "myapp"            # must equal app_name in myapp/urls.py
    def get_urls(self, page=None, language=None, **kwargs):
        return ["myapp.urls"]
```

```python
page = create_page("Log", "page.html", "en", apphook="MyApp", apphook_namespace="myapp", in_navigation=True)
```

- If `myapp/urls.py` sets `app_name`, `CMSApp.app_name` **and** `apphook_namespace=` are both required, or `{% url 'myapp:...' %}` raises `NoReverseMatch`.
- `cms.middleware.utils.ApphookReloadMiddleware` must be in `MIDDLEWARE`.
- In tests, call `reload_urlconf()` (`from cms.utils.apphook_reload import reload_urlconf`) after creating or changing apphook pages; the urlconf is cached.
