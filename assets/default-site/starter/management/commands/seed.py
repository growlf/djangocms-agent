"""One-step seeding: seed_pages then seed_site. Idempotent; safe to run on every start (SEED_ON_START=1)."""
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed the starter page tree and site content (runs seed_pages, then seed_site; idempotent)"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Passed to seed_site: clear and refill its placeholders")

    def handle(self, *args, reset=False, **kwargs):
        call_command("seed_pages", stdout=self.stdout)
        call_command("seed_site", reset=reset, stdout=self.stdout)
