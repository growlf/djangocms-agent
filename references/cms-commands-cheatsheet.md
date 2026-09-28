## CMS Commands Reference

### Management Commands

```bash
# CMS-specific commands
python manage.py cms check              # Validate CMS configuration
python manage.py cms fix_node_numbers   # Fix page tree node numbers
python manage.py cms list               # List all pages
python manage.py cms publish page slug  # Publish a page
python manage.py cms unpublish page slug  # Unpublish a page

# Cache management
python manage.py clear_cms_cache        # Clear CMS cache

# Static files
python manage.py collectstatic          # Collect static files
python manage.py collectstatic --check  # Check for missing static files

# Database
python manage.py migrate                # Run all migrations
python manage.py migrate cms            # Run CMS migrations only
python manage.py migrate --list cms     # List applied/unapplied CMS migrations
```

### Programmatic Page Creation

```python
# Via Django shell
python manage.py shell -c "
from cms.api import create_page, add_plugin
from django.contrib.sites.models import Site

site = Site.objects.get_current()

# Create a page with children
home = create_page('Home', 'page.html', 'en-us', site=site)
about = create_page('About', 'page.html', 'en-us', parent=home, site=site)
work = create_page('Work', 'page.html', 'en-us', parent=home, site=site)

# Add a text plugin to a placeholder
from cms.models import Placeholder
placeholder = Placeholder.objects.get(slot='body', page=about)
add_plugin(placeholder, 'TextPlugin', 'en-us', body='About content here')
"
```

### Common Troubleshooting

```bash
# Check for template errors
python manage.py check --deploy

# Check CMS-specific issues
python manage.py cms check

# Verify all apps are configured
python manage.py check

# Test with minimal settings
python manage.py check --settings=thenetyeti.settings.local
```
