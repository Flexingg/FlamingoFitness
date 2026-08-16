"""Create demo user accounts (admin + player) and integrations.

Usage:
    python manage.py create_demo_accounts

Creates:
  * an admin superuser  (admin / adminpass123)
  * a demo player       (player1 / playerpass123)
  * active Garmin / Peloton / Liftosaur / SparkyFitness integrations for player1
  * the Phase 9 (docs/15 §8) Gacha packs + gear catalog + campaign bosses
  * a demo PlayerProfile wallet + starter loadout + gyms for PvP
  * default PR Boss benchmarks (BossConfig)
  * the default Phase 8 challenge ("Calorie Torch"), the current open league
    week, a demo friendship (player1 <-> admin) and the "Flamingo Fam" flock

This command is idempotent and safe to run on every container startup.
It does NOT run any mock pollers or create activity data.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.models import (
    BossConfig,
    CampaignBoss,
    Challenge,
    Flock,
    FlockMembership,
    Friendship,
    GearItemDef,
    GearPackDef,
    Gym,
    PlayerProfile,
    Provider,
    UserGear,
    UserIntegration,
)

User = get_user_model()

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "adminpass123"

PLAYER_USERNAME = "player1"
PLAYER_PASSWORD = "playerpass123"

# Phase 9 (docs/15 §8): Gacha packs, gear catalog and campaign bosses.
# Crate packs drop from the WHOLE catalog (is_generic=True); theme packs drop
# only their own items filtered to their domains.
DEFAULT_PACKS = [
    {"slug": "starter_pack", "name": "Starter Pack", "price_tokens": 100,
     "draws": 2, "domains": [], "guaranteed_min_rarity": "common", "sort_order": 1},
    {"slug": "rare_crate", "name": "Rare Crate", "price_tokens": 150,
     "draws": 1, "domains": [], "guaranteed_min_rarity": "rare", "is_generic": True,
     "icon": "fa-box", "sort_order": 2,
     "description": "A no-frills crate that guarantees at least a Rare from the whole catalog."},
    {"slug": "epic_crate", "name": "Epic Crate", "price_tokens": 400,
     "draws": 1, "domains": [], "guaranteed_min_rarity": "epic", "is_generic": True,
     "icon": "fa-box", "sort_order": 3,
     "description": "Guarantees at least an Epic - bulk-buying makes it far better value."},
    {"slug": "iron_roost", "name": "Iron Roost", "price_tokens": 100,
     "draws": 1, "domains": ["strength"], "guaranteed_min_rarity": "common", "sort_order": 4},
    {"slug": "alchemist_pack", "name": "Alchemist's Pack", "price_tokens": 250,
     "draws": 3, "domains": ["nutrition", "hydration"], "guaranteed_min_rarity": "rare", "sort_order": 5},
    {"slug": "cardio_storm", "name": "Cardio Storm", "price_tokens": 100,
     "draws": 1, "domains": ["cardio"], "guaranteed_min_rarity": "common", "sort_order": 6},
    {"slug": "slumber_serum", "name": "Slumber Serum", "price_tokens": 100,
     "draws": 1, "domains": ["sleep"], "guaranteed_min_rarity": "common", "sort_order": 7},
    {"slug": "legendary_vault", "name": "Legendary Vault", "price_tokens": 500,
     "draws": 5, "domains": [], "guaranteed_min_rarity": "epic", "sort_order": 8},
    {"slug": "legendary_crate", "name": "Legendary Crate", "price_tokens": 800,
     "draws": 1, "domains": [], "guaranteed_min_rarity": "legendary", "is_generic": True,
     "icon": "fa-gem", "sort_order": 9,
     "description": "One guaranteed Legendary from the whole catalog. The lucky dip of a lifetime."},
]

DEFAULT_GEAR = [
    {"slug": "rook_helm", "name": "Rook Helm", "slot": "head", "rarity": "common",
     "icon": "fa-hat-cowboy",
     "effect_type": "domain_multiplier", "effect_domain": "strength", "effect_value": 1.05,
     "pack": "iron_roost", "weight": 100},
    {"slug": "beach_bandana", "name": "Beach Bandana", "slot": "head", "rarity": "common",
     "icon": "fa-hat-cowboy",
     "effect_type": "domain_multiplier", "effect_domain": "cardio", "effect_value": 1.05,
     "pack": "cardio_storm", "weight": 100},
    {"slug": "leviathan_cuirass", "name": "Leviathan Cuirass", "slot": "chest", "rarity": "epic",
     "icon": "fa-shirt",
     "effect_type": "domain_multiplier", "effect_domain": "strength", "effect_value": 1.7,
     "pack": "iron_roost", "weight": 30},
    {"slug": "swift_wind_band", "name": "Swift Wind Band", "slot": "accessory", "rarity": "epic",
     "icon": "fa-ring",
     "effect_type": "domain_multiplier", "effect_domain": "cardio", "effect_value": 1.8,
     "pack": "cardio_storm", "weight": 30},
    {"slug": "gauntlets_of_recharge", "name": "Gauntlets of Recharge", "slot": "left_hand", "rarity": "legendary",
     "icon": "fa-hand-fist",
     "effect_type": "synergy", "effect_domain": "strength", "effect_value": 2.5,
     "requires_sleep_efficiency": 0.85, "pack": "legendary_vault", "weight": 5},
    {"slug": "dumbbell_shield", "name": "Dumbbell Shield", "slot": "right_hand", "rarity": "epic",
     "icon": "fa-shield-halved",
     "effect_type": "domain_multiplier", "effect_domain": "strength", "effect_value": 1.6,
     "pack": "iron_roost", "weight": 25,
     "description": "A weight-plated tower shield that anchors your right hand."},
    {"slug": "oak_leg_plates", "name": "Oak Leg Plates", "slot": "legs", "rarity": "rare",
     "icon": "fa-person",
     "effect_type": "domain_multiplier", "effect_domain": "strength", "effect_value": 1.4,
     "pack": "iron_roost", "weight": 35,
     "description": "Sturdy leg greaves that help you squat deeper and stronger."},
    {"slug": "swift_stompers", "name": "Swift Stompers", "slot": "feet", "rarity": "rare",
     "icon": "fa-shoe-prints",
     "effect_type": "domain_multiplier", "effect_domain": "cardio", "effect_value": 1.3,
     "pack": "cardio_storm", "weight": 35,
     "description": "Feather-light runners that keep your cadence high."},
    {"slug": "pre_workout_nectar", "name": "Pre-Workout Nectar", "slot": "", "rarity": "rare",
     "icon": "fa-flask", "effect_type": "double_domain", "effect_domain": "cardio", "effect_value": 2.0,
     "is_consumable": True, "max_stack": 9, "pack": "alchemist_pack", "weight": 40},
    {"slug": "macro_potion", "name": "Macro-Potion", "slot": "", "rarity": "rare",
     "icon": "fa-vial", "effect_type": "shield_overage", "effect_value": 1.0,
     "is_consumable": True, "max_stack": 9, "pack": "alchemist_pack", "weight": 40},
]

DEFAULT_CAMPAIGN_BOSSES = [
    ("cardio", "ghastly_recliner", "The Ghastly Recliner", 2000, "endurance", [], [], {}),
    ("strength", "sir_skip_a_leg", "Sir Skip-a-Leg", 1500, "strength", [], ["strength"], {}),
    ("strength", "iron_couch_king", "The Iron Couch King", 2500, "strength", [], ["strength"], {}),
    ("strength", "deadlift_djinn", "The Deadlift Djinn", 4000, "strength", ["strength"], [], {}),
    ("nutrition", "carbo_hydra", "The Carbo-Hydra", 600, "nutrition", [], [], {"heal_on_overage": True}),
    ("hydration", "the_dehydrator", "The Dehydrator", 800, "hydration", ["hydration"], [], {"front_load_water_noon": True}),
    ("sleep", "restless_wraith", "The Restless Wraith", 300, "recovery", [], ["sleep"], {}),
]
class Command(BaseCommand):
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
            defaults={"email": "player1@example.com", "streak": 12},
        )
        if player_created:
            player.set_password(PLAYER_PASSWORD)
            player.save()
            self.stdout.write(self.style.SUCCESS(f"Created player: {PLAYER_USERNAME} / {PLAYER_PASSWORD}"))
        else:
            self.stdout.write(f"Player '{PLAYER_USERNAME}' already exists.")

        # Phase 9 packs, gear catalog & campaign bosses (idempotent by slug).
        created_packs = 0
        for defaults in list(DEFAULT_PACKS):
            defaults = dict(defaults)
            slug = defaults.pop("slug")
            _, created = GearPackDef.objects.get_or_create(slug=slug, defaults=defaults)
            created_packs += int(created)

        created_gear = 0
        gear_packs = {p.slug: p for p in GearPackDef.objects.all()}
        for entry in list(DEFAULT_GEAR):
            d = dict(entry)
            slug = d.pop("slug")
            pack_slug = d.pop("pack", None)
            d["pack"] = gear_packs.get(pack_slug) if pack_slug else None
            _, created = GearItemDef.objects.get_or_create(slug=slug, defaults=d)
            created_gear += int(created)

        created_bosses = 0
        order_by_campaign = {}
        for (campaign, slug, name, hp, element, weak, res, mech) in DEFAULT_CAMPAIGN_BOSSES:
            # Sequential per-campaign sort_order so conquering auto-advances to
            # the next boss in the campaign (docs/15 §5.4).
            order_by_campaign[campaign] = order_by_campaign.get(campaign, 0) + 1
            _, created = CampaignBoss.objects.get_or_create(
                slug=slug,
                defaults={"campaign": campaign, "name": name, "hp_total": hp,
                          "element": element, "weaknesses": weak,
                          "resistances": res, "mechanics": mech,
                          "sort_order": order_by_campaign[campaign]},
            )
            created_bosses += int(created)

        # Demo wallet + starter loadout (idempotent).
        PlayerProfile.objects.get_or_create(user=player)

        def _give_gear(slug, slot=None):
            gd = GearItemDef.objects.get(slug=slug)
            quantity = gd.max_stack if gd.is_consumable else 1
            own, _ = UserGear.objects.update_or_create(
                user=player, gear_def=gd,
                defaults={"rarity": gd.rarity, "quantity": quantity},
            )
            if slot is not None:
                UserGear.objects.filter(user=player, equipped_slot=slot).update(equipped_slot=None)
                own.equipped_slot = slot
                own.save(update_fields=["equipped_slot"])

        _give_gear("rook_helm", "head")
        _give_gear("leviathan_cuirass", "chest")
        _give_gear("swift_wind_band", "accessory")
        # A few unequipped pieces so the Inventory has things to equip straight away.
        _give_gear("dumbbell_shield")
        _give_gear("oak_leg_plates")
        _give_gear("swift_stompers")
        _give_gear("pre_workout_nectar")
        _give_gear("macro_potion")

        # Gyms for both demo users so PvP is alive on first boot.
        for u, nm in ((player, "Flamingo Arena"), (admin, "Iron Roost Gym")):
            Gym.objects.get_or_create(owner=u, defaults={"name": nm, "terrain": "strength"})

        # Active integrations so the pollers (and SparkyFitness bodyweight for
        # the PR Boss) have something to iterate.
        created_integrations = 0
        for provider in (Provider.GARMIN, Provider.PELOTON, Provider.LIFTOSAUR, Provider.SPARKYFITNESS):
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
        created_pr_bosses = 0
        for name, match, mult in default_bosses:
            _, created = BossConfig.objects.get_or_create(
                name=name,
                defaults={"exercise_match": match, "bodyweight_multiplier": mult},
            )
            created_pr_bosses += int(created)

        self.stdout.write(f"Gacha packs ensured ({created_packs} newly created).")
        self.stdout.write(f"Gear catalog ensured ({created_gear} newly created).")
        self.stdout.write(f"Campaign bosses ensured ({created_bosses} newly created).")
        self.stdout.write(f"PR Boss benchmarks ensured ({created_pr_bosses} newly created).")
        self.stdout.write(f"Integrations ensured ({created_integrations} newly created).")
        self._seed_phase8_social(admin, player)
        self.stdout.write(self.style.SUCCESS("Demo accounts created."))

    def _seed_phase8_social(self, admin, player):
        """Phase 8 (docs/13 §8): default challenge, league week, friendship,
        and the demo flock. Idempotent - safe on every startup."""
        from core.services.leagues import ensure_current_week

        # 1. The single default challenge: calories burned in the last 30 days.
        challenge, created = Challenge.objects.get_or_create(
            slug="calories_burned_30d",
            defaults={
                "name": "Calorie Torch",
                "description": "Most calories burned in the last 30 days. "
                "Every workout counts - keep the flame alive!",
                "icon": "fa-fire-flame-curved",
                "metric": Challenge.Metric.CALORIES_BURNED,
                "window_days": 30,
                "is_active": True,
                "sort_order": 1,
            },
        )
        if not created and not challenge.is_active:
            challenge.is_active = True
            challenge.save(update_fields=["is_active"])

        # 2. Ensure the current open league week exists (lazy-close stale ones).
        week = ensure_current_week()

        # 3. Demo friendship: player1 -> admin (accepted).
        Friendship.objects.get_or_create(
            from_user=player,
            to_user=admin,
            defaults={"status": Friendship.Status.ACCEPTED},
        )

        # 4. Demo flock "Flamingo Fam" owned by player1, admin as member.
        flock = Flock.objects.filter(name="Flamingo Fam").first()
        if flock is None:
            flock = Flock.objects.create(name="Flamingo Fam", created_by=player)
        FlockMembership.objects.get_or_create(
            user=player,
            defaults={"flock": flock, "role": FlockMembership.Role.OWNER},
        )
        FlockMembership.objects.get_or_create(
            user=admin,
            defaults={"flock": flock, "role": FlockMembership.Role.MEMBER},
        )

        self.stdout.write(
            f"Phase 8 social ensured (challenge='{challenge.slug}', "
            f"week={week.week_start}, flock='{flock.name}')."
        )

