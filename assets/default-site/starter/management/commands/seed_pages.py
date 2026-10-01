from django.core.management.base import BaseCommand
from django.db import transaction

from starter.seeding import ensure_page, get_user, publish

# (title, slug, template). The first entry becomes the home page. seed_site fills it and adds
# the About and Style & Capabilities pages; add your own pages here.
PAGES = [
    ("Home", "home", "landing.html"),
]


class Command(BaseCommand):
    help = "Create the starter page tree (idempotent, self-healing, publishes drafts)"

    def handle(self, *args, **kwargs):
        user = get_user()
        for i, (title, slug, template) in enumerate(PAGES):
            with transaction.atomic():
                page, _ = ensure_page(slug, title, template, user)
                if i == 0 and not page.is_home:
                    page.set_as_homepage()
                publish(page, user)
        self.stdout.write("seeded")
