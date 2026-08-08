"""Seed the database with demo users, integrations and data.

Usage:
    python manage.py seed_demo

Creates:
  * an admin superuser  (admin / adminpass123)
  * a demo player       (player1 / playerpass123)
  * active Garmin / Peloton / Liftosaur integrations for player1
  * runs the mock pollers once so RawActivityLog, XP, skill trees and
    readiness are all populated (makes the dashboard show live data).
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from core.tasks import poll_garmin, poll_liftosaur, poll_peloton, poll_sparkyfitness


class Command(BaseCommand):
    help = "Seed the database with demo users, integrations and data."

    def handle(self, *args, **options):
        self.stdout.write("Creating demo accounts...")
        from django.core.management import call_command
        call_command("create_demo_accounts")

        # Run the mock pollers synchronously to populate real-looking data.
        self.stdout.write("Running mock pollers...")
        poll_garmin()
        poll_peloton()
        poll_liftosaur()
        if settings.DEMO:
            self.stdout.write("DEMO=True — seeding SparkyFitness demo data.")
            poll_sparkyfitness()
        else:
            self.stdout.write("DEMO=False — skipping SparkyFitness demo poll.")
        self.stdout.write(self.style.SUCCESS("Demo data seeded. Polling complete."))
