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


class BadgeDef(models.Model):
    """Static achievement badge catalog (Roadmap idea #5).

    A badge is a *derived* milestone: its ``key`` maps to a check predicate in
    ``core/services/badges.py`` that reads data we already store (``User.streak``,
    ``RawActivityLog``, ``SkillTree``, ``BaseResource``, base level), so no new
    ingestion is required. Grants are recorded on :class:`UserBadge`.
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
        help_text='Rewards paid on close, e.g. {"time_speedups": 5, "materials": 25}.',
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
