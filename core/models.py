"""Core data models for Flamingo Fitness.

Phase 2 of the build sequence (docs/07_Next_Steps.md steps 5-7):

  * Step 5 - Custom User + UserIntegration (API credential storage)
  * Step 6 - RawActivityLog (JSONB ELT ingestion) + XPLedger
  * Step 7 - SkillTree + DailyReadiness

The BaseResource model backs the base-building meta-game (materials/energy).
"""

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

    def __str__(self):
        return f"{self.user.username} base: {self.materials} mat, {self.energy} en"

