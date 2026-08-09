"""Create demo user accounts (admin + player) and integrations.

Usage:
    python manage.py create_demo_accounts

Creates:
  * an admin superuser  (admin / adminpass123)
  * a demo player       (player1 / playerpass123)
  * active Garmin / Peloton / Liftosaur integrations for player1
  * the 9-entry BaseBuildingDef catalog (idempotent by slug)
  * demo BaseBuilding instances (lawn_chairs Lv1 + cabana Lv1 built)

This command is idempotent and safe to run on every container startup.
It does NOT run any mock pollers or create activity data.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    BaseBuilding,
    BaseBuildingDef,
    BaseResource,
    BossConfig,
    Provider,
    UserIntegration,
)

User = get_user_model()

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "adminpass123"

PLAYER_USERNAME = "player1"
PLAYER_PASSWORD = "playerpass123"

# Section 8 default catalog (docs/09_Base_Building_Meta_Game.md §8.1).
DEFAULT_BUILDINGS = [
    {
        "slug": "lawn_chairs",
        "name": "Lawn Chairs",
        "base_cost_materials": 10,
        "base_cost_energy": 5,
        "base_duration_hours": 0,
        "materials_per_day": 1,
        "xp_bonus_pct": 0,
        "max_level": 3,
        "requires_base_level": 0,
        "modality_affinity": None,
        "requires_blueprint": None,
        "sort_order": 1,
    },
    {
        "slug": "cabana",
        "name": "Cabana",
        "base_cost_materials": 40,
        "base_cost_energy": 10,
        "base_duration_hours": 6,
        "materials_per_day": 2,
        "xp_bonus_pct": 1,
        "max_level": 5,
        "requires_base_level": 0,
        "modality_affinity": None,
        "requires_blueprint": None,
        "sort_order": 2,
        "branch_choices": {"Materials": "cabana_mat", "XP": "cabana_xp"},
    },
    {
        "slug": "cabana_mat",
        "name": "Beach Cabana",
        "base_cost_materials": 50,
        "base_cost_energy": 12,
        "base_duration_hours": 8,
        "materials_per_day": 6,
        "xp_bonus_pct": 0,
        "max_level": 5,
        "requires_base_level": 0,
        "modality_affinity": None,
        "requires_blueprint": None,
        "sort_order": 3,
    },
    {
        "slug": "cabana_xp",
        "name": "VIP Cabana",
        "base_cost_materials": 50,
        "base_cost_energy": 12,
        "base_duration_hours": 8,
        "materials_per_day": 1,
        "xp_bonus_pct": 4,
        "max_level": 5,
        "requires_base_level": 0,
        "modality_affinity": None,
        "requires_blueprint": None,
        "sort_order": 4,
    },
    {
        "slug": "juice_bar",
        "name": "Juice Bar",
        "base_cost_materials": 60,
        "base_cost_energy": 15,
        "base_duration_hours": 8,
        "materials_per_day": 3,
        "xp_bonus_pct": 2,
        "max_level": 5,
        "requires_base_level": 1,
        "modality_affinity": "cardio",
        "requires_blueprint": None,
        "sort_order": 5,
    },
    {
        "slug": "recovery_pool",
        "name": "Recovery Pool",
        "base_cost_materials": 70,
        "base_cost_energy": 20,
        "base_duration_hours": 12,
        "materials_per_day": 0,
        "xp_bonus_pct": 1,
        "max_level": 3,
        "requires_base_level": 2,
        "modality_affinity": None,
        "requires_blueprint": None,
        "sort_order": 6,
        "rest_day_bonus_add": 5,
    },
    {
        "slug": "pool_deck",
        "name": "Pool Deck",
        "base_cost_materials": 140,
        "base_cost_energy": 30,
        "base_duration_hours": 16,
        "materials_per_day": 6,
        "xp_bonus_pct": 4,
        "max_level": 5,
        "requires_base_level": 3,
        "modality_affinity": None,
        "requires_blueprint": None,
        "sort_order": 7,
    },
    {
        "slug": "vip_lounge",
        "name": "VIP Lounge",
        "base_cost_materials": 380,
        "base_cost_energy": 70,
        "base_duration_hours": 48,
        "materials_per_day": 14,
        "xp_bonus_pct": 9,
        "max_level": 5,
        "requires_base_level": 6,
        "modality_affinity": "strength",
        "requires_blueprint": None,
        "sort_order": 8,
    },
    {
        "slug": "gold_flamingo",
        "name": "Gold Statue",
        "base_cost_materials": 400,
        "base_cost_energy": 80,
        "base_duration_hours": 72,
        "materials_per_day": 50,
        "xp_bonus_pct": 10,
        "max_level": 3,
        "requires_base_level": 8,
        "modality_affinity": None,
        "requires_blueprint": "golden_flamingo",
        "sort_order": 9,
    },
]


class Command(BaseCommand):
    help = "Create demo user accounts, integrations, and base-building catalog/instances (idempotent, no pollers)."

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

        # Seed the 9-entry catalog idempotently by slug.
        created_defs = 0
        for defaults in DEFAULT_BUILDINGS:
            slug = defaults.pop("slug")
            def_obj, created = BaseBuildingDef.objects.get_or_create(
                slug=slug,
                defaults=defaults,
            )
            created_defs += int(created)

        self.stdout.write(f"Catalog seeded ({created_defs} newly created).")

        # Demo instances: lawn_chairs Lv1 and cabana Lv1 (both built, instant production).
        now = timezone.now()
        demo_instances = [
            {
                "slug": "lawn_chairs",
                "defaults": {
                    "level": 1,
                    "target_level": 0,
                    "construction_started_at": None,
                    "last_produced_at": now,
                },
            },
            {
                "slug": "cabana",
                "defaults": {
                    "level": 1,
                    "target_level": 0,
                    "construction_started_at": None,
                    "last_produced_at": now,
                },
            },
        ]
        created_instances = 0
        for cfg in demo_instances:
            slug = cfg.pop("slug")
            def_obj = BaseBuildingDef.objects.get(slug=slug)
            _, created = BaseBuilding.objects.update_or_create(
                user=player,
                building_def=def_obj,
                defaults=cfg["defaults"],
            )
            created_instances += int(created)

        # Base resources for the player (extend existing defaults).
        BaseResource.objects.get_or_create(
            user=player,
            defaults={
                "materials": 150,
                "energy": 45,
                "time_speedups": 5,
                "blueprints": {"golden_flamingo": 1},
            },
        )

        # Active integrations so the pollers (and SparkyFitness bodyweight for
        # the PR Boss) have something to iterate.
        created_integrations = 0
        for provider in (
            Provider.GARMIN,
            Provider.PELOTON,
            Provider.LIFTOSAUR,
            Provider.SPARKYFITNESS,
        ):
            _, created = UserIntegration.objects.get_or_create(
                user=player,
                provider=provider,
                defaults={"is_active": True},
            )
            created_integrations += int(created)

        # Seed default admin-configurable PR Boss benchmarks (idempotent).
        default_bosses = [
            ("Bench Press", "Bench Press", 1.5),
            ("Squat", "Squat", 2.0),
            ("Deadlift", "Deadlift", 2.5),
            ("Overhead Press", "Overhead Press", 1.0),
        ]
        created_bosses = 0
        for name, match, mult in default_bosses:
            _, created = BossConfig.objects.get_or_create(
                name=name,
                defaults={
                    "exercise_match": match,
                    "bodyweight_multiplier": mult,
                },
            )
            created_bosses += int(created)

        self.stdout.write(f"Integrations ensured ({created_integrations} newly created).")
        self.stdout.write(f"PR Boss benchmarks ensured ({created_bosses} newly created).")
        self.stdout.write(f"Demo building instances ensured ({created_instances} newly created).")
        self.stdout.write(self.style.SUCCESS("Demo accounts created."))
