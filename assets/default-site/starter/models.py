from cms.models import CMSPlugin
from django.db import models


class HtmlBlock(CMSPlugin):
    """Staff-authored raw HTML (forms, Bootstrap components, data-bs-* attributes).

    djangocms-text sanitises its HTML and strips forms and data attributes, so rich Bootstrap
    markup needs this plugin. Rendered unescaped: only grant it to trusted editors.
    """

    html = models.TextField(help_text="Trusted HTML, rendered as-is.")

    def __str__(self):
        return self.html[:40]
