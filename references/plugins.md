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
