### Recommended CMS Plugins (stable, maintained)
```python
dependencies = [
    # Proven on cms 5.1.3 + Django 5.2 (TheNetYeti runs these): djangocms-text, djangocms-link, djangocms-snippet, djangocms-versioning, django-filer
    # Verified 2026-09-30 in a scratch project: system check passes, migrate runs, no pending migrations (NOT render-tested):
    #   djangocms-alias, -picture, -video, -file, -style, -bootstrap5 (pulls in djangocms-icon), -googlemap
    # Core (always include)
    "djangocms-alias",      # Reusable content fragments
    "djangocms-link",       # Links with rich options
    "djangocms-picture",    # Image plugin
    "djangocms-text",       # WYSIWYG text editor
    
    # Media & content
    "djangocms-video",      # Video embedding
    "djangocms-file",       # File downloads
    "djangocms-style",      # Text styling classes
    
    # UI components
    "djangocms-bootstrap5", # Bootstrap grid/components
    # djangocms-social: DO NOT USE — 0.4a1 imports ugettext_lazy, removed in Django 4; crashes on Django 5.2
    
    # Advanced (optional)
    "djangocms-googlemap",  # Embedded maps
    # djangocms-form: not on PyPI (the name does not exist); pick a forms plugin and test it before listing
]

# Transitive pins the site needed:
# djangocms-attributes-field, django-filer, django-polymorphic, django-mptt,
# easy-thumbnails, pillow, lxml, nh3, django-fsm-2
```

Note: installing the plugins above also installs the legacy `djangocms-text-ckeditor` as a dependency. Do not add `djangocms_text_ckeditor` to `INSTALLED_APPS` next to `djangocms_text`.
