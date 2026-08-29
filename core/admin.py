from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    BadgeDef,
    BattleLog,
    BossConfig,
    CampaignBoss,
    CampaignProgress,
    Challenge,
    DailyReadiness,
    Flock,
    FlockInvite,
    FlockMembership,
    Friendship,
    GearItemDef,
    GearPackDef,
    Gym,
    GymOccupation,
    LeagueResult,
    LeagueWeek,
    PlayerProfile,
    PvPMatch,
    RawActivityLog,
    SkillTree,
    ScrapShopItem,
    User,
    UserBadge,
    UserGear,
    UserIntegration,
    WaterBottle,
    XPLedger,
)


@admin.register(User)
class FlamingoUserAdmin(UserAdmin):
    """Expose our custom streak/avatar fields in the Django admin panel."""

    fieldsets = UserAdmin.fieldsets + (
        ("Flamingo Fitness", {"fields": ("streak", "avatar", "theme")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Flamingo Fitness", {"fields": ("streak", "avatar", "theme")}),
    )
    list_display = ("username", "streak", "theme", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "is_superuser", "theme")
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
                    '{"type": "activity_logs", "minimum": 50} | '
                    '{"type": "skill_level", "modality": "strength", "minimum": 5} | '
                    '{"type": "all_modalities", "minimum": 3} | '
                    '{"type": "perfect_days", "days": 7} | '
                    '{"type": "total_xp", "minimum": 500} | '
                    '{"type": "time_window", "before_hour": 6} or '
                    '{"type": "time_window", "after_hour": 21} | '
                    '{"type": "conquests", "minimum": 5} (PvE) | '
                    '{"type": "pvp_wins", "minimum": 3} | '
                    '{"type": "gear_owned", "minimum": 10} | '
                    '{"type": "league_results", "minimum": 1} or '
                    '{"type": "league_tier", "tier": "gold"}. '
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
# ---------------------------------------------------------------------------
# Phase 9 (docs/15): Token, Gacha & Battle
# ---------------------------------------------------------------------------
@admin.register(PlayerProfile)
class PlayerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "tokens", "stamina", "scraps", "total_conquests", "pvp_wins", "pvp_losses")
    search_fields = ("user__username",)
    readonly_fields = ("created_at",)


@admin.register(GearPackDef)
class GearPackDefAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "price_tokens", "draws", "guaranteed_min_rarity", "is_generic", "is_active")
    list_filter = ("is_active", "is_generic", "guaranteed_min_rarity")
    search_fields = ("slug", "name")


@admin.register(GearItemDef)
class GearItemDefAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "slot", "rarity", "effect_type", "effect_domain",
                     "effect_value", "is_consumable", "is_active")
    list_filter = ("rarity", "effect_type", "slot", "is_active")
    search_fields = ("slug", "name")


@admin.register(ScrapShopItem)
class ScrapShopItemAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "cost_scraps", "available_days", "reward_type",
                     "reward_value", "is_active")
    list_filter = ("is_active", "reward_type")
    search_fields = ("slug", "name")


@admin.register(UserGear)
class UserGearAdmin(admin.ModelAdmin):
    list_display = ("user", "gear_def", "rarity", "quantity", "equipped_slot", "obtained_at")
    list_filter = ("rarity", "equipped_slot")
    search_fields = ("user__username", "gear_def__slug")


@admin.register(CampaignBoss)
class CampaignBossAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "campaign", "element", "hp_total", "is_active", "sort_order")
    list_filter = ("campaign", "element", "is_active")
    search_fields = ("slug", "name")


@admin.register(CampaignProgress)
class CampaignProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "campaign", "boss", "damage_dealt", "total_hp", "conquered")
    list_filter = ("campaign", "conquered")
    search_fields = ("user__username",)


@admin.register(BattleLog)
class BattleLogAdmin(admin.ModelAdmin):
    list_display = ("user", "campaign", "boss", "date", "base_damage", "total_damage", "boss_heal", "tokens_won")
    list_filter = ("campaign",)
    search_fields = ("user__username",)


@admin.register(Gym)
class GymAdmin(admin.ModelAdmin):
    list_display = ("owner", "name", "terrain", "defense_set", "is_active")
    list_filter = ("terrain", "is_active")
    search_fields = ("owner__username", "name")

    @admin.display(boolean=True, description="Defense set")
    def defense_set(self, obj):
        return bool(obj.defense_snapshot)


@admin.register(GymOccupation)
class GymOccupationAdmin(admin.ModelAdmin):
    list_display = ("gym", "occupant", "held_until", "last_token_paid")


@admin.register(PvPMatch)
class PvPMatchAdmin(admin.ModelAdmin):
    list_display = ("attacker", "defender", "gym", "attacker_power", "defender_power", "did_win")
    list_filter = ("did_win",)
    search_fields = ("attacker__username", "defender__username")



@admin.register(WaterBottle)
class WaterBottleAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "capacity_oz", "sort_order")
    list_filter = ("user",)
    search_fields = ("user__username", "name")
