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


class Provider(models.TextChoices):
    """External data sources we poll via Celery."""

    GARMIN = "garmin", "Garmin"
    PELOTON = "peloton", "Peloton"
    LIFTOSAUR = "liftosaur", "Liftosaur"
    SPARKYFITNESS = "sparkyfitness", "SparkyFitness"
    HOME_ASSISTANT = "home_assistant", "Home Assistant"


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


class BaseResource(models.Model):
    """Base-building meta-game resources owned by a user."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="base_resources"
    )
    materials = models.PositiveIntegerField(default=0)
    energy = models.PositiveIntegerField(default=0)
    time_speedups = models.PositiveIntegerField(default=0)
    # Phase 7 (docs/09): passive-regen + idempotency + state trackers.
    energy_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Passive energy regen checkpoint (never stored while above the cap).",
    )
    last_daily_harvest = models.DateField(
        null=True,
        blank=True,
        help_text="Last date the daily XP -> materials dividend was minted (idempotency).",
    )
    last_rest_bonus_date = models.DateField(
        null=True,
        blank=True,
        help_text="Last date the rest-day energy spike was granted (idempotency).",
    )
    blueprints = models.JSONField(
        default=dict,
        help_text="Rare blueprint ownership, e.g. {'golden_flamingo': 1} (unlocks prestige defs).",
    )
    active_buffs = models.JSONField(
        default=dict,
        help_text="Modality production buffs, e.g. {'strength_buff_expiry': 'iso-date'}.",
    )
    last_milestone_celebrated = models.IntegerField(
        default=0,
        help_text="Base level whose confetti celebration was acknowledged (5, 10, ...).",
    )

    def __str__(self):
        return f"{self.user.username} base: {self.materials} mat, {self.energy} en"


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


class BaseBuildingDef(models.Model):
    """Admin-configurable catalog for the base-building meta-game (Phase 7).

    One row per building type ("The Flamingo Club"): costs, construction
    duration, daily material production, XP bonus, branch options, modality
    affinity, blueprint gates and rest-day recovery additions. Tuned in the
    Django admin (`/admin/`).
    """

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=40, default="fa-umbrella-beach")
    base_cost_materials = models.PositiveIntegerField(default=40)
    base_cost_energy = models.PositiveIntegerField(default=10)
    base_duration_hours = models.PositiveIntegerField(
        default=6, help_text="0 = instant micro-build."
    )
    materials_per_day = models.PositiveIntegerField(default=0)
    xp_bonus_pct = models.PositiveIntegerField(default=0)
    max_level = models.PositiveIntegerField(default=5)
    requires_base_level = models.PositiveIntegerField(default=0)
    requires_blueprint = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="e.g. 'golden_flamingo' - must be owned in BaseResource.blueprints.",
    )
    modality_affinity = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="e.g. 'strength' / 'cardio' - matches an active_buffs key for 1.2x production.",
    )
    branch_choices = models.JSONField(
        default=dict,
        help_text="Level-3 evolution menu, e.g. {'Materials': 'cabana_mat', 'XP': 'cabana_xp'}.",
    )
    rest_day_bonus_add = models.PositiveIntegerField(
        default=0,
        help_text="Extra rest-day energy granted while this building is owned (Recovery Pool).",
    )
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def cost_for_level(self, target_level):
        """Material + energy cost for building/upgrading TO ``target_level``.

        Both scale +40% per level above 1.
        """
        scale = 1 + 0.4 * (target_level - 1)
        return round(self.base_cost_materials * scale), round(
            self.base_cost_energy * scale
        )

    def duration_for_level(self, target_level):
        return self.base_duration_hours * target_level

    def bonus_pct_for_level(self, target_level):
        return self.xp_bonus_pct * target_level

    def __str__(self):
        return f"{self.name} ({self.slug})"


class BaseBuilding(models.Model):
    """A user's instance of a BaseBuildingDef (per-user level/construction state).

    ``level == 0`` means never built. While constructing, ``target_level`` holds
    the level under construction and ``construction_started_at`` +
    ``construction_duration_hours`` describe the timer.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="base_buildings"
    )
    building_def = models.ForeignKey(
        BaseBuildingDef, on_delete=models.CASCADE, related_name="instances"
    )
    level = models.PositiveIntegerField(
        default=0, help_text="Built level (0 = never built)."
    )
    target_level = models.PositiveIntegerField(
        default=0, help_text="In-construction target level."
    )
    construction_started_at = models.DateTimeField(null=True, blank=True)
    construction_duration_hours = models.PositiveIntegerField(default=0)
    last_produced_at = models.DateTimeField(
        null=True, blank=True, help_text="Idle-accrual checkpoint for production."
    )
    custom_color = models.CharField(
        max_length=7, default="#FF69B4", help_text="Neon customization (#RRGGBB)."
    )
    staff_friend_id = models.IntegerField(
        null=True, blank=True, help_text="Social +10% production boost avatar id."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "building_def"], name="unique_user_building_def"
            )
        ]

    def is_constructing(self, now=None):
        """True while the construction timer is running (lazy - never stored)."""
        if not self.construction_started_at:
            return False
        now = now or timezone.now()
        return now < self.construction_started_at + timedelta(
            hours=self.construction_duration_hours
        )

    def __str__(self):
        return f"{self.user.username} {self.building_def.slug} Lv{self.level}"

