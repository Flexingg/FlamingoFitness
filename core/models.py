"""Core data models for Flamingo Fitness.

Phase 2 of the build sequence (docs/07_Next_Steps.md steps 5-7):

  * Step 5 - Custom User + UserIntegration (API credential storage)
  * Step 6 - RawActivityLog (JSONB ELT ingestion) + XPLedger
  * Step 7 - SkillTree + DailyReadiness

The BaseResource model backs the base-building meta-game (materials/energy).
"""

from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


def default_now():
    return timezone.now()


class Modality(models.TextChoices):
    """The modality skill trees."""

    STRENGTH = "strength", "Strength"
    ENDURANCE = "endurance", "Endurance"
    NUTRITION = "nutrition", "Nutrition"
    HYDRATION = "hydration", "Hydration"
    RECOVERY = "recovery", "Recovery"


class Theme(models.TextChoices):
    """User-selectable app appearance (light / dark / device / time)."""

    LIGHT = "light", "Light"
    DARK = "dark", "Dark"
    DEVICE = "device", "Device"
    TIME = "time", "Time"


class Provider(models.TextChoices):
    """External data sources we poll via Celery or sync via mobile."""

    GARMIN = "garmin", "Garmin"
    PELOTON = "peloton", "Peloton"
    LIFTOSAUR = "liftosaur", "Liftosaur"
    SPARKYFITNESS = "sparkyfitness", "SparkyFitness"
    HOME_ASSISTANT = "home_assistant", "Home Assistant"
    HEALTH_CONNECT = "health_connect", "Health Connect"
    HEALTHKIT = "healthkit", "HealthKit"
    MANUAL = "manual", "Manual"


class User(AbstractUser):
    """Custom user model (Step 5). Extends Django's AbstractUser."""

    streak = models.PositiveIntegerField(
        default=0,
        help_text="Current consecutive-day streak, protected by readiness.",
    )
    avatar = models.URLField(
        blank=True,
        default="https://api.dicebear.com/7.x/avataaars/svg?seed=Flamingo",
        help_text="Avatar image URL shown on leaderboards and the dashboard.",
    )
    theme = models.CharField(
        max_length=10,
        choices=Theme.choices,
        default=Theme.DEVICE,
        help_text=(
            "Appearance preference: force Light or Dark, follow the device, "
            "or switch by time of day (dark 6pm-6am)."
        ),
    )

    @property
    def total_xp(self):
        return XPLedger.objects.filter(user=self).aggregate(
            total=models.Sum("amount")
        )["total"] or 0

    def __str__(self):
        return self.username


class UserIntegration(models.Model):
    """Stores API credentials/tokens for each external provider (Step 5)."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="integrations"
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    credentials = models.JSONField(
        default=dict,
        blank=True,
        help_text="OAuth tokens / API keys for this provider.",
    )
    is_active = models.BooleanField(default=True)
    last_polled = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "provider"], name="unique_user_provider"
            )
        ]
        ordering = ["provider"]

    def __str__(self):
        return f"{self.user.username} / {self.provider}"


class RawActivityLog(models.Model):
    """Raw ELT inbox. Webhooks and pollers drop unprocessed JSONB here.

    The gamification service layer (Step 13) picks these up, converts them
    into XPLedger entries, and marks them processed.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="raw_logs"
    )
    source = models.CharField(max_length=20, choices=Provider.choices)
    event_type = models.CharField(
        max_length=40,
        help_text="e.g. cardio, strength, sleep, body_battery, macro, scale",
    )
    payload = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=default_now)
    processed = models.BooleanField(
        default=False,
        help_text="True once the XP service has converted this log to XP.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.user.username} / {self.source} / {self.event_type}"


class XPLedger(models.Model):
    """Immutable XP ledger entries produced by the gamification service."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="xp_entries"
    )
    raw_log = models.ForeignKey(
        RawActivityLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="xp_entries",
    )
    modality = models.CharField(max_length=20, choices=Modality.choices)
    amount = models.IntegerField(
        help_text="Positive XP award. Negative entries possible for corrections."
    )
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["modality"]),
        ]

    def __str__(self):
        return f"{self.user.username} +{self.amount} {self.modality} XP"

class SkillTree(models.Model):
    """Per-user, per-modality progression track (Step 7 / Step 14)."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="skill_trees"
    )
    modality = models.CharField(max_length=20, choices=Modality.choices)
    level = models.PositiveIntegerField(default=1)
    xp = models.PositiveIntegerField(
        default=0,
        help_text="XP accumulated *within* the current level (0..XP_PER_LEVEL).",
    )
    total_xp = models.PositiveIntegerField(
        default=0,
        help_text="Lifetime XP in this modality (drives level ups).",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "modality"], name="unique_user_modality"
            )
        ]
        ordering = ["modality"]

    @property
    def progress_pct(self):
        from .services.gamification import XP_PER_LEVEL

        return int((self.xp / XP_PER_LEVEL) * 100)

    def __str__(self):
        return f"{self.user.username} {self.modality} Lv{self.level}"


class DailyReadiness(models.Model):
    """Readiness engine output (Step 7 / Step 15)."""

    class StreakRequirement(models.TextChoices):
        REST_DAY = "rest_day", "Rest Day"
        TRAIN = "train", "Train"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="readiness_records"
    )
    date = models.DateField()
    score = models.PositiveIntegerField(
        help_text="0-100 readiness score computed from sleep + body battery."
    )
    streak_requirement = models.CharField(
        max_length=20, choices=StreakRequirement.choices,
        default=StreakRequirement.TRAIN,
    )
    message = models.TextField(blank=True, default="")
    body_battery = models.PositiveIntegerField(null=True, blank=True)
    sleep_hours = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "date"], name="unique_user_date_readiness"
            )
        ]
        ordering = ["-date"]

    def __str__(self):
        return f"{self.user.username} readiness {self.score} ({self.streak_requirement})"


class BossConfig(models.Model):
    """Admin-configurable PR Boss thresholds.

    A boss is a benchmark lift, e.g. "Bench Press 1.5x your bodyweight." The
    threshold is computed as the user's latest bodyweight (from SparkyFitness
    check-in measurements) multiplied by ``bodyweight_multiplier``. The user's
    best lift (heaviest set, or Epley est. 1RM) is compared against it.

    Configure entries in the Django admin (`/admin/`).
    """

    name = models.CharField(max_length=120, help_text="Boss name, e.g. 'Bench Press'.")
    exercise_match = models.CharField(
        max_length=120,
        help_text="Substring matched (case-insensitive) against Liftosaur exercise "
        "names, e.g. 'Bench Press'.",
    )
    bodyweight_multiplier = models.FloatField(
        default=1.5, help_text="Lift goal = bodyweight x multiplier (e.g. 1.5x BW)."
    )
    unit = models.CharField(max_length=8, default="lb", help_text="lb or kg")
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.name} ({self.bodyweight_multiplier}x BW)"


# ---------------------------------------------------------------------------
# Phase 9 (docs/15): Token, Gacha & Battle system
# ---------------------------------------------------------------------------
class Rarity(models.TextChoices):
    COMMON = "common", "Common"
    RARE = "rare", "Rare"
    EPIC = "epic", "Epic"
    LEGENDARY = "legendary", "Legendary"


class GearSlot(models.TextChoices):
    HEAD = "head", "Head"
    CHEST = "chest", "Chest"
    LEFT_HAND = "left_hand", "Left Hand"
    RIGHT_HAND = "right_hand", "Right Hand"
    LEGS = "legs", "Legs"
    FEET = "feet", "Feet"
    ACCESSORY = "accessory", "Accessory"


class Campaign(models.TextChoices):
    """PvE campaign tracks (map 1:1 to the existing five modalities).

    ``SLEEP`` maps to ``Modality.RECOVERY`` in the gamification pipeline.
    """

    CARDIO = "cardio", "Cardio"
    STRENGTH = "strength", "Weightlifting"
    NUTRITION = "nutrition", "Nutrition"
    HYDRATION = "hydration", "Hydration"
    SLEEP = "sleep", "Sleep"


class Element(models.TextChoices):
    """PvP elemental types (the element wheel, docs/15 §3.6)."""

    ENDURANCE = "endurance", "Endurance"
    STRENGTH = "strength", "Strength"
    NUTRITION = "nutrition", "Nutrition"
    HYDRATION = "hydration", "Hydration"
    RECOVERY = "recovery", "Recovery"


class PlayerProfile(models.Model):
    """Token + stamina wallet (replaces the Phase 7 BaseResource wallet)."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="combat_profile"
    )
    tokens = models.PositiveIntegerField(
        default=300, help_text="Premium currency spent in the Gacha Shop."
    )
    stamina = models.PositiveIntegerField(
        default=3, help_text="Daily siege-attack budget (refills each day)."
    )
    stamina_updated_at = models.DateTimeField(null=True, blank=True)
    last_token_harvest = models.DateField(
        null=True, blank=True, help_text="Daily token-dividend idempotency stamp."
    )
    scraps = models.PositiveIntegerField(
        default=0,
        help_text="Scrap currency earned by recycling gear; spent in the Scrap Shop.",
    )
    last_scraps_stamp = models.DateField(
        null=True, blank=True, help_text="Scrap-shop rotation idempotency stamp."
    )
    active_buffs = models.JSONField(
        default=dict,
        help_text="Dated combat buffs, e.g. {'cardio_double_date': 'YYYY-MM-DD'.",
    )
    total_conquests = models.PositiveIntegerField(default=0)
    pvp_wins = models.PositiveIntegerField(default=0)
    pvp_losses = models.PositiveIntegerField(default=0)
    onboarded = models.BooleanField(
        default=False,
        help_text="Guided first-flight onboarding completed (docs/17 #91).",
    )
    source_preferences = models.JSONField(
        default=dict,
        blank=True,
        help_text="User preferences for data provider per modality.",
    )
    notification_preferences = models.JSONField(
        default=dict,
        blank=True,
        help_text="Push notification settings per category and quiet hours.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} profile ({self.tokens} tokens)"


class WaterBottle(models.Model):
    """A user's custom water-bottle size for quick one-tap water logging."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="water_bottles"
    )
    name = models.CharField(max_length=50, default="Bottle")
    capacity_oz = models.FloatField(help_text="Capacity in fluid ounces")
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.name} ({self.capacity_oz}oz)"


class GearPackDef(models.Model):
    """A themed Gacha pack (e.g. Iron Roost, Alchemist's Pack)."""

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=60, default="fa-box-open")
    price_tokens = models.PositiveIntegerField(default=100)
    draws = models.PositiveIntegerField(default=1)
    domains = models.JSONField(
        default=list, blank=True, help_text="Targeted Campaign values."
    )
    guaranteed_min_rarity = models.CharField(
        max_length=20, choices=Rarity.choices, default=Rarity.COMMON
    )
    is_generic = models.BooleanField(
        default=False, help_text="Crate-style pack that drops from the whole gear catalog (ignores the pack FK)."
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "slug"]

    def __str__(self):
        return self.name


class GearItemDef(models.Model):
    """Gear / consumable catalog (admin-configurable, like the old defs)."""

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    slot = models.CharField(
        max_length=20, choices=GearSlot.choices, blank=True, default=""
    )
    rarity = models.CharField(max_length=20, choices=Rarity.choices, default=Rarity.COMMON)
    effect_type = models.CharField(
        max_length=30,
        default="domain_multiplier",
        help_text=(
            "domain_multiplier | synergy | double_domain | shield_overage. "
            "Consumables use double_domain / shield_overage."
        ),
    )
    effect_domain = models.CharField(
        max_length=20, choices=Campaign.choices, null=True, blank=True
    )
    effect_value = models.FloatField(default=1.0)
    effect_params = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Extensible JSON for richer effects, e.g. "
            "{'scales_from': 'strength'} for effect_type=scales_with."
        ),
    )
    requires_sleep_efficiency = models.FloatField(
        null=True, blank=True, help_text="e.g. 0.85 gates a synergy item."
    )
    pack = models.ForeignKey(
        GearPackDef, null=True, blank=True, on_delete=models.SET_NULL, related_name="items"
    )
    weight = models.PositiveIntegerField(default=100, help_text="Relative drop weight in a pack.")
    is_consumable = models.BooleanField(default=False)
    max_stack = models.PositiveIntegerField(default=1)
    icon = models.CharField(max_length=60, default="fa-shirt")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "slug"]

    def __str__(self):
        return f"{self.name} ({self.rarity})"


class UserGear(models.Model):
    """A user's owned gear item (or consumable stack)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="gear")
    gear_def = models.ForeignKey(GearItemDef, on_delete=models.CASCADE, related_name="owned")
    rarity = models.CharField(max_length=20, choices=Rarity.choices, default=Rarity.COMMON)
    quantity = models.PositiveIntegerField(default=1)
    obtained_at = models.DateTimeField(auto_now_add=True)
    equipped_slot = models.CharField(
        max_length=20, choices=GearSlot.choices, null=True, blank=True
    )

    class Meta:
        ordering = ["-obtained_at"]

    def __str__(self):
        return f"{self.user.username}: {self.gear_def.slug} x{self.quantity}"


class ScrapShopItem(models.Model):
    """A purchasable item in the rotating Scrap Shop (docs/16).

    Availability rotates by day of week (``available_days`` is a JSON list of
    ``date.weekday()`` ints, Monday=0 … Sunday=6). Only items whose mask matches
    today are offered, which gives the shop a visible daily rotation.
    """

    class RewardType(models.TextChoices):
        TOKENS = "tokens", "Tokens"
        STAMINA = "stamina", "Stamina"
        PACK = "pack", "Pack draws"
        STREAK_FREEZE = "streak_freeze", "Streak Freeze"

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    icon = models.CharField(max_length=60, default="fa-box-open")
    description = models.TextField(blank=True)
    cost_scraps = models.PositiveIntegerField(default=50)
    available_days = models.JSONField(
        default=list,
        blank=True,
        help_text="date.weekday() ints (0=Mon..6=Sun) this item is offered.",
    )
    reward_type = models.CharField(
        max_length=20, choices=RewardType.choices, default=RewardType.TOKENS
    )
    reward_value = models.FloatField(default=0)
    pack = models.ForeignKey(
        GearPackDef, null=True, blank=True, on_delete=models.SET_NULL
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "slug"]

    def __str__(self):
        return f"{self.name} ({self.cost_scraps} scraps)"



class CampaignBoss(models.Model):
    """A PvE boss definition (docs/15 §4.6)."""

    campaign = models.CharField(max_length=20, choices=Campaign.choices)
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    icon = models.CharField(max_length=60, default="fa-dragon")
    hp_total = models.BigIntegerField(default=100_000)
    element = models.CharField(max_length=20, choices=Element.choices)
    weaknesses = models.JSONField(
        default=list, blank=True, help_text="Campaign domains dealing 2x damage."
    )
    resistances = models.JSONField(
        default=list, blank=True, help_text="Campaign domains dealing 0.5x damage."
    )
    mechanics = models.JSONField(
        default=dict,
        blank=True,
        help_text='{"front_load_water_noon": true, "heal_on_overage": true}.',
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["campaign", "sort_order"]

    def __str__(self):
        return f"{self.name} ({self.campaign})"


class CampaignProgress(models.Model):
    """One user's multi-day siege state per campaign (docs/15 §4.7)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sieges")
    campaign = models.CharField(max_length=20, choices=Campaign.choices)
    boss = models.ForeignKey(
        CampaignBoss, null=True, blank=True, on_delete=models.SET_NULL
    )
    damage_dealt = models.BigIntegerField(default=0)
    total_hp = models.BigIntegerField(default=0)
    conquered = models.BooleanField(default=False)
    engaged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "campaign"], name="unique_user_campaign")
        ]

    def __str__(self):
        return f"{self.user.username} / {self.campaign} siege"


class BattleLog(models.Model):
    """One siege attack result (history + token payout)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="battle_logs")
    campaign = models.CharField(max_length=20, choices=Campaign.choices)
    boss = models.ForeignKey(
        CampaignBoss,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="battle_logs",
        help_text="The specific boss this attack hit (docs/17 #33/#34 sieges).",
    )
    date = models.DateField()
    base_damage = models.BigIntegerField(default=0)
    gear_multiplier = models.FloatField(default=1.0)
    boss_multiplier = models.FloatField(default=1.0)
    total_damage = models.BigIntegerField(default=0)
    boss_heal = models.BigIntegerField(default=0)
    tokens_won = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} {self.campaign} -{self.total_damage}"


class Gym(models.Model):
    """A single-player PvP Gym defenders park their avatar at (docs/15 §4.9)."""

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="gyms")
    name = models.CharField(max_length=80)
    terrain = models.CharField(
        max_length=20, choices=Element.choices, default=Element.STRENGTH
    )
    defense_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Frozen loadout + 7-day consistency used for async resolution.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner"], name="unique_gym_owner")
        ]

    def __str__(self):
        return f"{self.name} ({self.owner.username})"


class GymOccupation(models.Model):
    """Who currently holds a Gym and until when (passive token yield)."""

    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name="occupations")
    occupant = models.ForeignKey(User, on_delete=models.CASCADE, related_name="gym_turf")
    held_until = models.DateTimeField()
    last_token_paid = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.occupant.username} holds {self.gym.name}"


class PvPMatch(models.Model):
    """An instant asynchronous gym-battle resolution."""

    attacker = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pvp_attacks")
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name="matches")
    defender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pvp_defenses")
    attacker_power = models.FloatField(default=0.0)
    defender_power = models.FloatField(default=0.0)
    did_win = models.BooleanField(default=False)
    token_stake = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.attacker.username} v {self.defender.username} ({'W' if self.did_win else 'L'})"


class MarketplaceListing(models.Model):
    """Player gear marketplace listing (Roadmap item #5)."""

    seller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="marketplace_listings"
    )
    gear_item = models.ForeignKey(
        GearItemDef, on_delete=models.CASCADE, related_name="marketplace_listings"
    )
    user_gear = models.ForeignKey(
        UserGear, on_delete=models.SET_NULL, null=True, blank=True, related_name="marketplace_entries"
    )
    rarity = models.CharField(max_length=20, default="common")
    price_type = models.CharField(
        max_length=10,
        choices=[("tokens", "Tokens"), ("scraps", "Scraps")],
        default="tokens",
    )
    price_amount = models.PositiveIntegerField(default=10)
    is_active = models.BooleanField(default=True)
    buyer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_purchases",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sold_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.seller.username}: {self.gear_item.name} ({self.rarity}) for {self.price_amount} {self.price_type}"


class BadgeDef(models.Model):
    """Static achievement badge catalog (Roadmap idea #5).

    A badge is a *derived* milestone: its ``key`` maps to a check predicate in
    ``core/services/badges.py`` that reads data we already store (``User.streak``,
    ``RawActivityLog``, ``SkillTree``, ``PlayerProfile``, and siege / PvP / gear /
    league state), so no new ingestion is required. Grants are recorded on
    :class:`UserBadge`.
    """

    key = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=80)
    description = models.CharField(
        max_length=255, blank=True, help_text="Shown on the badge tile."
    )
    icon = models.CharField(
        max_length=60,
        default="fa-medal",
        help_text="FontAwesome icon class, e.g. 'fa-fire' (no 'fa-solid' prefix).",
    )
    category = models.CharField(max_length=40, default="Milestones")
    points = models.PositiveIntegerField(
        default=10,
        help_text="Badge Points awarded for earning this badge (scale by difficulty).",
    )
    rule = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'Declarative earn rule evaluated by core/services/badges.py, e.g. '
            '{"type": "streak", "minimum": 30}. See the README "Achievement '
            'badges" section for all rule types. An empty rule can never be earned.'
        ),
    )
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(
        default=True, help_text="Inactive badges are hidden from players."
    )

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class UserBadge(models.Model):
    """A badge granted to a user (idempotent - unique per user/badge)."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="badges"
    )
    badge = models.ForeignKey(
        BadgeDef, on_delete=models.CASCADE, related_name="grants"
    )
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "badge"], name="unique_user_badge")
        ]
        ordering = ["-awarded_at"]

    def __str__(self):
        return f"{self.user.username} / {self.badge.name}"


# ---------------------------------------------------------------------------
# Phase 8 (docs/13): Leagues, Challenges & Flocks
# ---------------------------------------------------------------------------
class LeagueTier(models.TextChoices):
    """Weekly league tiers, awarded by weekly Effort XP (docs/13 §3.1)."""

    BRONZE = "bronze", "Bronze"
    SILVER = "silver", "Silver"
    GOLD = "gold", "Gold"
    DIAMOND = "diamond", "Diamond"
    FLAMINGO_LEGEND = "flamingo_legend", "Flamingo Legend"


class LeagueWeek(models.Model):
    """One calendar week (Monday-anchored) of the Effort XP league.

    Completes the parked Step 8b (docs/07): the weekly leaderboard now has
    persistence. Weeks open lazily via ``ensure_current_week`` and are closed
    by the Monday beat task (or lazily on read), which snapshots ranks into
    :class:`LeagueResult` and pays the top-3 rewards.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    week_start = models.DateField(
        unique=True, help_text="Monday of the league week (local time)."
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.OPEN
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-week_start"]

    @property
    def week_end(self):
        return self.week_start + timedelta(days=6)

    def __str__(self):
        return f"Week of {self.week_start.isoformat()} ({self.status})"


class LeagueResult(models.Model):
    """Per-user snapshot of one closed league week (rank / tier / reward)."""

    week = models.ForeignKey(
        LeagueWeek, on_delete=models.CASCADE, related_name="results"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="league_results"
    )
    xp = models.IntegerField(default=0, help_text="Effort XP earned that week.")
    rank = models.PositiveIntegerField(default=0)
    tier = models.CharField(
        max_length=20, choices=LeagueTier.choices, default=LeagueTier.BRONZE
    )
    reward = models.JSONField(
        default=dict,
        blank=True,
        help_text='Rewards paid on close, e.g. {"tokens": 5}.',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["week", "user"], name="unique_week_user_result")
        ]
        ordering = ["rank"]

    def __str__(self):
        return f"{self.user.username} #{self.rank} week {self.week.week_start}"


class Challenge(models.Model):
    """A rolling community challenge (docs/13 §3.3).

    Exactly ONE challenge may be active at a time; ``save()`` deactivates all
    others when this row is activated, so the admin UI cannot double-activate.
    Progress is derived live from data we already store (no new ingestion).
    """

    class Metric(models.TextChoices):
        CALORIES_BURNED = "calories_burned", "Calories Burned"

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=60, default="fa-fire-flame-curved")
    metric = models.CharField(
        max_length=30, choices=Metric.choices, default=Metric.CALORIES_BURNED
    )
    window_days = models.PositiveIntegerField(
        default=30, help_text="Rolling window the metric is aggregated over."
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Single-active rule (docs/13 §3.4): activating one deactivates the rest.
        if self.is_active:
            Challenge.objects.exclude(pk=self.pk).filter(is_active=True).update(
                is_active=False
            )

    def __str__(self):
        return self.name

class Friendship(models.Model):
    """A friend request / accepted friendship between two users.

    ``status="pending"`` is a request from ``from_user`` to ``to_user``;
    ``status="accepted"`` means both are friends. A pair is friends iff an
    accepted row exists in EITHER direction - always query both.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"

    from_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="friend_requests_sent"
    )
    to_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="friend_requests_received"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["from_user", "to_user"], name="unique_friendship_direction"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.from_user.username} -> {self.to_user.username} ({self.status})"


class Flock(models.Model):
    """A small social group (Duolingo-family sized, up to 8 members)."""

    name = models.CharField(max_length=80)
    icon = models.CharField(max_length=60, default="fa-dove")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flocks_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class FlockMembership(models.Model):
    """One flock per user (OneToOne) - join/leave never juggles rows."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MEMBER = "member", "Member"

    flock = models.ForeignKey(
        Flock, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="flock_membership"
    )
    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.MEMBER
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["joined_at"]

    def __str__(self):
        return f"{self.user.username} in {self.flock.name} ({self.role})"


class FlockInvite(models.Model):
    """An invitation for a user to join a flock (owner-initiated)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    flock = models.ForeignKey(
        Flock, on_delete=models.CASCADE, related_name="invites"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="flock_invites"
    )
    invited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flock_invites_sent",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["flock", "user"], name="unique_flock_invite")
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} -> {self.flock.name} ({self.status})"


class PushDevice(models.Model):
    """A mobile or web client push notification device endpoint."""

    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"
        WEB = "web", "Web"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="push_devices"
    )
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(
        max_length=10, choices=Platform.choices, default=Platform.ANDROID
    )
    device_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self):
        return f"{self.user.username} ({self.platform}: {self.token[:12]}...)"


class PushNotificationLog(models.Model):
    """A recorded push notification or intelligent reminder."""

    class Category(models.TextChoices):
        FOOD = "food", "Food & Meals"
        HYDRATION = "hydration", "Hydration"
        WORKOUT = "workout", "Workout & Activity"
        SLEEP = "sleep", "Sleep & Wind-down"
        STREAK = "streak", "Streak Preservation"
        BOUNTY = "bounty", "Bounties & Duels"
        GENERAL = "general", "General"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="push_notifications"
    )
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.GENERAL
    )
    title = models.CharField(max_length=150)
    body = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"[{self.category}] {self.user.username}: {self.title}"


class Bounty(models.Model):
    """An interactive fitness wager, solo contract, or 1v1 friend duel (Roadmap N8)."""

    class BountyType(models.TextChoices):
        SOLO = "solo", "Solo Contract"
        OPEN = "open", "Open Board Bounty"
        DUEL = "duel", "1v1 Duel"
        FLOCK = "flock", "Flock Raid Bounty"

    class TargetType(models.TextChoices):
        STEPS = "steps", "Steps"
        CARDIO_MINUTES = "cardio_minutes", "Cardio Minutes"
        STRENGTH_VOLUME = "strength_volume", "Strength Volume (lbs)"
        WATER_ML = "water_ml", "Hydration (ml)"
        PROTEIN_G = "protein_g", "Protein (g)"
        CALORIES_BURNED = "calories_burned", "Active Calories Burned"
        WORKOUT_COUNT = "workout_count", "Workouts Logged"
        SLEEP_HOURS = "sleep_hours", "Sleep (Hours)"

    class Status(models.TextChoices):
        OPEN = "open", "Open (Awaiting Opponent)"
        ACTIVE = "active", "In Progress"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    creator = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="bounties_created"
    )
    opponent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bounties_challenged",
    )
    flock = models.ForeignKey(
        Flock,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flock_bounties",
    )

    bounty_type = models.CharField(
        max_length=15, choices=BountyType.choices, default=BountyType.OPEN
    )
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    target_type = models.CharField(max_length=25, choices=TargetType.choices)
    target_value = models.FloatField(
        help_text="Target numerical goal (e.g. 10000 steps, 25000 lbs, 3000 ml water)."
    )

    wager_tokens = models.PositiveIntegerField(
        default=0, help_text="Tokens staked per participant in escrow."
    )
    wager_scraps = models.PositiveIntegerField(
        default=0, help_text="Scraps staked per participant in escrow."
    )
    reward_xp = models.PositiveIntegerField(
        default=50, help_text="XP awarded upon verified completion."
    )
    bonus_tokens = models.PositiveIntegerField(
        default=10, help_text="System-funded bonus tokens added to prize pool."
    )

    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.OPEN
    )
    duration_hours = models.PositiveIntegerField(
        default=24, help_text="Duration in hours from when bounty becomes active."
    )
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)

    winner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bounties_won",
    )
    is_claimed = models.BooleanField(
        default=False, help_text="True once winner has claimed prize pot."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.bounty_type}] {self.title} ({self.status}) - {self.creator.username}"


class BountyParticipant(models.Model):
    """Tracks a user's verified progress inside an active bounty window."""

    bounty = models.ForeignKey(
        Bounty, on_delete=models.CASCADE, related_name="participants"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="bounty_participations"
    )

    current_value = models.FloatField(
        default=0.0, help_text="Total verified progress logged during active window."
    )
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    payout_claimed = models.BooleanField(default=False)

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["bounty", "user"], name="unique_bounty_participant"
            )
        ]
        ordering = ["-joined_at"]

    def __str__(self):
        return f"{self.user.username} in {self.bounty.title}: {self.current_value}/{self.bounty.target_value}"

