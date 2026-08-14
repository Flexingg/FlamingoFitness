from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    BaseBuilding,
    BaseBuildingDef,
    BaseResource,
    BadgeDef,
    BossConfig,
    Challenge,
    DailyReadiness,
    Flock,
    FlockInvite,
    FlockMembership,
    Friendship,
    LeagueResult,
    LeagueWeek,
    RawActivityLog,
    SkillTree,
    User,
    UserBadge,
    UserIntegration,
    XPLedger,
)


@admin.register(User)
class FlamingoUserAdmin(UserAdmin):
    """Expose our custom streak/avatar fields in the Django admin panel."""

    fieldsets = UserAdmin.fieldsets + (
        ("Flamingo Fitness", {"fields": ("streak", "avatar")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Flamingo Fitness", {"fields": ("streak", "avatar")}),
    )
    list_display = ("username", "streak", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("username", "email")


@admin.register(UserIntegration)
class UserIntegrationAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "is_active", "last_polled", "updated_at")
    list_filter = ("provider", "is_active")
    search_fields = ("user__username",)


@admin.register(RawActivityLog)
class RawActivityLogAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "source",
        "event_type",
        "processed",
        "occurred_at",
        "created_at",
    )
    list_filter = ("source", "event_type", "processed")
    search_fields = ("user__username",)
    readonly_fields = ("created_at",)


@admin.register(XPLedger)
class XPLedgerAdmin(admin.ModelAdmin):
    list_display = ("user", "modality", "amount", "description", "created_at")
    list_filter = ("modality",)
    search_fields = ("user__username", "description")
    readonly_fields = ("created_at",)


@admin.register(SkillTree)
class SkillTreeAdmin(admin.ModelAdmin):
    list_display = ("user", "modality", "level", "xp", "total_xp", "progress_pct")
    list_filter = ("modality",)
    search_fields = ("user__username",)


@admin.register(DailyReadiness)
class DailyReadinessAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "date",
        "score",
        "streak_requirement",
        "body_battery",
        "sleep_hours",
    )
    list_filter = ("date", "streak_requirement")
    search_fields = ("user__username",)


@admin.register(BaseResource)
class BaseResourceAdmin(admin.ModelAdmin):
    list_display = ("user", "materials", "energy", "time_speedups")
    search_fields = ("user__username",)


@admin.register(BossConfig)
class BossConfigAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "exercise_match",
        "bodyweight_multiplier",
        "unit",
        "is_active",
        "sort_order",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "exercise_match")


@admin.register(BadgeDef)
class BadgeDefAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "category", "points", "sort_order", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("key", "name", "description")
    list_editable = ("points", "sort_order", "is_active")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "key",
                    "name",
                    "description",
                    "icon",
                    "category",
                    "points",
                    "sort_order",
                    "is_active",
                ),
            },
        ),
        (
            "Earn rule (how the badge is unlocked)",
            {
                "fields": ("rule",),
                "description": (
                    "A JSON object evaluated against the user's data. Examples: "
                    '{"type": "streak", "minimum": 30} | '
                    '{"type": "base_level", "minimum": 10} | '
                    '{"type": "blueprints", "minimum": 3} | '
                    '{"type": "activity_logs", "minimum": 50} | '
                    '{"type": "skill_level", "modality": "strength", "minimum": 5} | '
                    '{"type": "all_modalities", "minimum": 3} | '
                    '{"type": "perfect_days", "days": 7} | '
                    '{"type": "total_xp", "minimum": 500} | '
                    '{"type": "time_window", "before_hour": 6} or '
                    '{"type": "time_window", "after_hour": 21}. '
                    "Leave empty to keep a badge unearnable. See README "
                    "'Achievement badges' for the full reference."
                ),
            },
        ),
    )


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ("user", "badge", "awarded_at")
    list_filter = ("badge",)
    search_fields = ("user__username", "badge__name")
    readonly_fields = ("awarded_at",)


@admin.register(BaseBuildingDef)
class BaseBuildingDefAdmin(admin.ModelAdmin):
    list_display = (
        "slug",
        "name",
        "base_cost_materials",
        "base_cost_energy",
        "base_duration_hours",
        "materials_per_day",
        "xp_bonus_pct",
        "requires_base_level",
        "modality_affinity",
        "requires_blueprint",
        "is_active",
        "sort_order",
    )
    list_filter = ("is_active",)
    search_fields = ("slug", "name")
    ordering = ("sort_order", "id")


@admin.register(BaseBuilding)
class BaseBuildingAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "building_def",
        "level",
        "target_level",
        "construction_started_at",
        "custom_color",
        "staff_friend_id",
        "created_at",
    )
    list_filter = ("building_def",)
    search_fields = ("user__username", "building_def__slug")


# ---------------------------------------------------------------------------
# Phase 8 (docs/13): Leagues, Challenges & Flocks
# ---------------------------------------------------------------------------
@admin.register(LeagueWeek)
class LeagueWeekAdmin(admin.ModelAdmin):
    list_display = ("week_start", "status", "closed_at")
    list_filter = ("status",)


@admin.register(LeagueResult)
class LeagueResultAdmin(admin.ModelAdmin):
    list_display = ("week", "rank", "user", "xp", "tier", "reward")
    list_filter = ("tier", "week")
    search_fields = ("user__username",)


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = (
        "slug",
        "name",
        "metric",
        "window_days",
        "is_active",
        "sort_order",
    )
    list_filter = ("metric", "is_active")
    search_fields = ("slug", "name")
    list_editable = ("is_active", "sort_order")


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ("from_user", "to_user", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("from_user__username", "to_user__username")


@admin.register(Flock)
class FlockAdmin(admin.ModelAdmin):
    list_display = ("name", "icon", "created_by", "created_at")
    search_fields = ("name",)


@admin.register(FlockMembership)
class FlockMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "flock", "role", "joined_at")
    list_filter = ("role", "flock")
    search_fields = ("user__username", "flock__name")


@admin.register(FlockInvite)
class FlockInviteAdmin(admin.ModelAdmin):
    list_display = ("user", "flock", "invited_by", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("user__username", "flock__name")
