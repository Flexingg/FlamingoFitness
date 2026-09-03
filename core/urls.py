"""URL routes for the `core` app."""
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views

urlpatterns = [
    # Auth / account creation
    path("signup/", views.signup, name="signup"),
    path(
        "login/",
        LoginView.as_view(template_name="core/login.html"),
        name="login",
    ),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    path("profile/avatar", views.avatar_upload, name="avatar_upload"),
    # API (Steps 16-18)
    path("dashboard/state", views.dashboard_state, name="dashboard_state"),
    path("onboarded", views.complete_onboarding, name="complete_onboarding"),
    path("nutrition/", views.nutrition_state, name="nutrition_state"),
    path("nutrition/recent-foods/", views.nutrition_recent_foods, name="nutrition_recent_foods"),
    path("nutrition/search-foods/", views.nutrition_search_foods, name="nutrition_search_foods"),
    path("nutrition/ai-generate-food/", views.nutrition_ai_generate_food, name="nutrition_ai_generate_food"),
    path("nutrition/create-food/", views.nutrition_create_food, name="nutrition_create_food"),
    path("nutrition/barcode/", views.nutrition_barcode_lookup, name="nutrition_barcode_lookup"),
    path("nutrition/quick-log/", views.nutrition_quick_log, name="nutrition_quick_log"),
    path("nutrition/entries/update/", views.nutrition_entry_update, name="nutrition_entry_update"),
    path("nutrition/entries/delete/", views.nutrition_entry_delete, name="nutrition_entry_delete"),
    path("nutrition/entries/copy/", views.nutrition_entry_copy, name="nutrition_entry_copy"),
    path("nutrition/snaps/", views.nutrition_snaps_list, name="nutrition_snaps_list"),
    path("nutrition/snaps/upload/", views.nutrition_snap_upload, name="nutrition_snap_upload"),
    path("nutrition/snaps/<int:draft_id>/commit/", views.nutrition_snap_commit, name="nutrition_snap_commit"),
    path("nutrition/snaps/<int:draft_id>/delete/", views.nutrition_snap_delete, name="nutrition_snap_delete"),
    path("hydration/", views.hydration_state, name="hydration_state"),
    path("hydration/water/add", views.water_add, name="water_add"),
    path("hydration/water/remove", views.water_remove, name="water_remove"),
    path("hydration/bottles/", views.water_bottles, name="water_bottles"),
    path(
        "hydration/bottles/<int:bottle_id>/delete",
        views.water_bottle_delete,
        name="water_bottle_delete",
    ),
    path("endurance/", views.endurance_state, name="endurance_state"),
    path("strength/", views.strength_state, name="strength_state"),
    path("boss/", views.boss_state, name="boss_state"),
    path("recovery/", views.recovery_state, name="recovery_state"),
        path("leaderboard/weekly", views.leaderboard_weekly, name="leaderboard_weekly"),
    # Achievement badges (Roadmap idea #5)
    path("badges/", views.badges_state, name="badges_state"),
    # Phase 8: Leagues, Challenges & Flocks (docs/13)
    path("leagues/", views.leagues_state, name="leagues_state"),
    path("challenges/", views.challenges_state, name="challenges_state"),
    path("social/", views.social_state_view, name="social_state"),
    path("friends/request", views.friends_request, name="friends_request"),
    path("friends/respond", views.friends_respond, name="friends_respond"),
    path("friends/remove", views.friends_remove, name="friends_remove"),
    path("flocks/create", views.flocks_create, name="flocks_create"),
    path("flocks/invite", views.flocks_invite, name="flocks_invite"),
    path("flocks/respond", views.flocks_respond, name="flocks_respond"),
    path("flocks/leave", views.flocks_leave, name="flocks_leave"),
    # Top-nav stat explainers (click streak / materials / energy badges)
    path("stats/<str:stat>/", views.stat_info, name="stat_info"),
    path(
        "webhooks/home-assistant",
        views.home_assistant_webhook,
        name="home_assistant_webhook",
    ),
    # Manual Quick Log & Historical Queue
    path("log/quick/", views.quick_log, name="quick_log"),
    path("queue/missing-logs/", views.missing_logs_queue, name="missing_logs_queue"),
    # Mobile App Health Connect sync
    path("sync/health", views.sync_health_data, name="sync_health_data"),
    # Profile & Source routing
    path("profile/sources/", views.source_preferences_view, name="source_preferences"),
    path("foods/search/", views.foods_search, name="foods_search"),
    # Mobile Push Notifications & Intelligent Reminders
    path("notifications/preferences/", views.notification_preferences_view, name="notification_preferences"),
    path("notifications/register/", views.notification_register_device, name="notification_register_device"),
    path("notifications/intelligent-prompt/", views.notification_intelligent_prompt, name="notification_intelligent_prompt"),
    path("notifications/history/", views.notification_history_view, name="notification_history"),
    path("notifications/test/", views.notification_test_send, name="notification_test_send"),
    # Marketplace (Roadmap item #5)
    path("marketplace/state", views.marketplace_state_view, name="marketplace_state"),
    path("marketplace/list", views.marketplace_list_view, name="marketplace_list"),
    path("marketplace/buy", views.marketplace_buy_view, name="marketplace_buy"),
    path("marketplace/cancel", views.marketplace_cancel_view, name="marketplace_cancel"),
    # Bounties & 1v1 Duels (Roadmap N8)
    path("bounties/state", views.bounties_state_view, name="bounties_state"),
    path("bounties/create", views.create_bounty_view, name="create_bounty"),
    path("bounties/<int:bounty_id>/accept", views.accept_bounty_view, name="accept_bounty"),
    path("bounties/<int:bounty_id>/cancel", views.cancel_bounty_view, name="cancel_bounty"),
    path("bounties/<int:bounty_id>/claim", views.claim_bounty_view, name="claim_bounty"),
    # Phase 9 (docs/15): Token, Gacha & Battle
    path("battle/state", views.battle_state, name="battle_state"),
    path("battle/campaign/<str:campaign>/", views.battle_campaign, name="battle_campaign"),
    path("battle/leaderboard/<str:campaign>/", views.battle_leaderboard, name="battle_leaderboard"),
    path("battle/history/<str:campaign>/", views.battle_history, name="battle_history"),
    path("battle/engage", views.battle_engage, name="battle_engage"),
    path("battle/attack", views.battle_attack, name="battle_attack"),
    path("shop/state", views.shop_state, name="shop_state"),
    path("shop/open", views.shop_open, name="shop_open"),
    path("shop/consume", views.shop_consume, name="shop_consume"),
    path("scrap/recycle", views.scrap_recycle, name="scrap_recycle"),
    path("scrap/shop/state", views.scrap_shop, name="scrap_shop"),
    path("scrap/shop/buy", views.scrap_buy, name="scrap_buy"),
    path("loadout/state", views.loadout_state, name="loadout_state"),
    path("loadout/equip", views.loadout_equip, name="loadout_equip"),
    path("loadout/unequip", views.loadout_unequip, name="loadout_unequip"),
    path("pvp/state", views.pvp_state, name="pvp_state"),
    path("pvp/defend", views.pvp_defend, name="pvp_defend"),
    # Panel HTML partials (docs/19 #12)
    path("panel/<str:name>/", views.panel_view, name="panel_view"),
    # Dashboard page (Step 19)
    path("", views.dashboard_page, name="dashboard"),
]
