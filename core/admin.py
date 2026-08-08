from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    BaseResource,
    BossConfig,
    DailyReadiness,
    RawActivityLog,
    SkillTree,
    User,
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
