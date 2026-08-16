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

import json
from pathlib import Path

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
    ScrapShopItem,
    UserGear,
    UserIntegration,
)

User = get_user_model()

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "adminpass123"

PLAYER_USERNAME = "player1"
PLAYER_PASSWORD = "playerpass123"

# ===========================================================================
# Seed data lives in config/seeds/*.json (NOT built into Python) - docs/16.
#
#   config/seeds/packs.json           -> GearPackDef catalog (DEFAULT_PACKS)
#   config/seeds/gear_items.json      -> GearItemDef catalog (DEFAULT_GEAR)
#   config/seeds/scrap_shop.json      -> ScrapShopItem catalog (DEFAULT_SCRAP_SHOP)
#   config/seeds/campaign_bosses.json -> CampaignBoss catalog (DEFAULT_CAMPAIGN_BOSSES)
#   config/seeds/boss_configs.json    -> PR BossConfig catalog (DEFAULT_BOSS_CONFIGS)
#   config/seeds/challenges.json      -> Challenge catalog (DEFAULT_CHALLENGES)
#
# Edit the Google Sheet and export it with tools/code.gs, then paste the
# resulting JSON into those files and re-run create_demo_accounts (idempotent).
# ===========================================================================
SEED_DIR = Path(__file__).resolve().parents[3] / "config" / "seeds"


def _load_seed_json(name):
    with (SEED_DIR / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


DEFAULT_PACKS = _load_seed_json("packs.json")
DEFAULT_GEAR = _load_seed_json("gear_items.json")
DEFAULT_SCRAP_SHOP = _load_seed_json("scrap_shop.json")

DEFAULT_CAMPAIGN_BOSSES = _load_seed_json("campaign_bosses.json")
DEFAULT_BOSS_CONFIGS = _load_seed_json("boss_configs.json")
DEFAULT_CHALLENGES = _load_seed_json("challenges.json")

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

        # Scrap Shop (rotating, weekday-gated) catalog - idempotent by slug.
        created_scrap = 0
        scrap_packs = {p.slug: p for p in GearPackDef.objects.all()}
        for entry in list(DEFAULT_SCRAP_SHOP):
            d = dict(entry)
            slug = d.pop("slug")
            pack_slug = d.pop("pack", None)
            d["pack"] = scrap_packs.get(pack_slug) if pack_slug else None
            _, created = ScrapShopItem.objects.get_or_create(slug=slug, defaults=d)
            created_scrap += int(created)

        created_bosses = 0
        order_by_campaign = {}
        for boss in DEFAULT_CAMPAIGN_BOSSES:
            # Sequential per-campaign sort_order so conquering auto-advances to
            # the next boss in the campaign (docs/15 §5.4).
            campaign = boss["campaign"]
            order_by_campaign[campaign] = order_by_campaign.get(campaign, 0) + 1
            _, created = CampaignBoss.objects.get_or_create(
                slug=boss["slug"],
                defaults={"campaign": campaign, "name": boss["name"], "hp_total": boss["hp_total"],
                          "element": boss["element"], "weaknesses": boss["weaknesses"],
                          "resistances": boss["resistances"], "mechanics": boss["mechanics"],
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
        # New-effect demo gear (docs/16) - one per type.
        _give_gear("stone_grip_gauntlets", "left_hand")  # flat_bonus
        _give_gear("warmup_crossfit_band", "right_hand")  # scales_with
        _give_gear("endurance_anklets", "feet")  # stamina_cap
        _give_gear("gilded_ledger")  # token_multiplier (in inventory to equip)
        _give_gear("adrenaline_shot")  # stamina_refund (consumable)
        _give_gear("coin_pouch_opener")  # grant_tokens (consumable)

        # Give the demo player a small scrap wallet so the Scrap Shop is usable.
        profile_player = PlayerProfile.objects.get(user=player)
        if profile_player.scraps < 60:
            profile_player.scraps = 60
            profile_player.save(update_fields=["scraps"])

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
        created_pr_bosses = 0
        for cfg in DEFAULT_BOSS_CONFIGS:
            _, created = BossConfig.objects.get_or_create(
                name=cfg["name"],
                defaults={"exercise_match": cfg["exercise_match"],
                          "bodyweight_multiplier": cfg["bodyweight_multiplier"]},
            )
            created_pr_bosses += int(created)

        self.stdout.write(f"Gacha packs ensured ({created_packs} newly created).")
        self.stdout.write(f"Gear catalog ensured ({created_gear} newly created).")
        self.stdout.write(f"Scrap shop ensured ({created_scrap} newly created).")
        self.stdout.write(f"Campaign bosses ensured ({created_bosses} newly created).")
        self.stdout.write(f"PR Boss benchmarks ensured ({created_pr_bosses} newly created).")
        self.stdout.write(f"Integrations ensured ({created_integrations} newly created).")
        self._seed_phase8_social(admin, player)
        self.stdout.write(self.style.SUCCESS("Demo accounts created."))

    def _seed_phase8_social(self, admin, player):
        """Phase 8 (docs/13 §8): default challenge, league week, friendship,
        and the demo flock. Idempotent - safe on every startup."""
        from core.services.leagues import ensure_current_week

        # 1. Default challenge(s) from config/seeds/challenges.json (idempotent).
        challenge = None
        for default in DEFAULT_CHALLENGES:
            d = dict(default)
            slug = d.pop("slug")
            challenge, created = Challenge.objects.get_or_create(slug=slug, defaults=d)
            if not created and not challenge.is_active:
                challenge.is_active = True
                challenge.save(update_fields=["is_active"])
        if challenge is None:
            challenge = Challenge.objects.first()

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

