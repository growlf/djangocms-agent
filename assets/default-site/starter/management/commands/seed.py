"""One-step seeding: seed_pages then seed_site. Idempotent.

With --first-run-only it does nothing when the site already has its home page, so a container started
with SEED_ON_START=1 seeds a fresh database once and never touches editors' later changes (a placeholder
an editor emptied on purpose is NOT refilled on restart). Without the flag it runs both seeds again,
which refills any empty placeholder of the pages they own.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand

from starter.seeding import page_for


class Command(BaseCommand):
    help = "Seed the starter page tree and site content (runs seed_pages, then seed_site; idempotent)"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Passed to seed_site: clear and refill its placeholders")
        parser.add_argument("--first-run-only", action="store_true",
                            help="Skip everything when the home page already exists (used by SEED_ON_START)")

    def handle(self, *args, reset=False, first_run_only=False, **kwargs):
        if first_run_only and page_for("home") is not None:
            self.stdout.write("home page exists: not seeding (run seed_pages / seed_site / seed to refill)")
            return
        call_command("seed_pages", stdout=self.stdout)
        call_command("seed_site", reset=reset, stdout=self.stdout)
