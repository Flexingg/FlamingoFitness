"""Create demo user accounts (admin + player) and integrations.

Usage:
    python manage.py create_demo_accounts

Creates:
  * an admin superuser  (admin / adminpass123)
  * a demo player       (player1 / playerpass123)
  * active Garmin / Peloton / Liftosaur integrations for player1

This command is idempotent and safe to run on every container startup.
It does NOT run any mock pollers or create activity data.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.models import BaseResource, Provider, UserIntegration

User = get_user_model()

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "adminpass123"

PLAYER_USERNAME = "player1"
PLAYER_PASSWORD = "playerpass123"


class Command(BaseCommand):
    help = "Create demo user accounts and integrations (idempotent, no pollers)."

    def handle(self, *args, **options):
        # Admin superuser
        admin, admin_created = User.objects.get_or_create(
            username=ADMIN_USERNAME,
            defaults={"is_staff": True, "is_superuser": True, "email": "admin@example.com"},
        )
        if admin_created:
            admin.set_password(ADMIN_PASSWORD)
            admin.save()
            self.stdout.write(self.style.SUCCESS(f"Created superuser: {ADMIN_USERNAME} / {ADMIN_PASSWORD}"))
        else:
            self.stdout.write(f"Superuser '{ADMIN_USERNAME}' already exists.")

        # Demo player
        player, player_created = User.objects.get_or_create(
            username=PLAYER_USERNAME,
            defaults={
                "email": "player1@example.com",
                "streak": 12,
            },
        )
        if player_created:
            player.set_password(PLAYER_PASSWORD)
            player.save()
            self.stdout.write(self.style.SUCCESS(f"Created player: {PLAYER_USERNAME} / {PLAYER_PASSWORD}"))
        else:
            self.stdout.write(f"Player '{PLAYER_USERNAME}' already exists.")

        # Base resources for the player
        BaseResource.objects.get_or_create(
            user=player, defaults={"materials": 150, "energy": 45}
        )

        # Active integrations so the pollers have something to iterate
        created_integrations = 0
        for provider in (Provider.GARMIN, Provider.PELOTON, Provider.LIFTOSAUR):
            _, created = UserIntegration.objects.get_or_create(
                user=player,
                provider=provider,
                defaults={"is_active": True},
            )
            created_integrations += int(created)
        self.stdout.write(f"Integrations ensured ({created_integrations} newly created).")
        self.stdout.write(self.style.SUCCESS("Demo accounts created."))
