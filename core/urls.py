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
    path("nutrition/", views.nutrition_state, name="nutrition_state"),
    path("hydration/", views.hydration_state, name="hydration_state"),
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
    # Phase 9 (docs/15): Token, Gacha & Battle
    path("battle/state", views.battle_state, name="battle_state"),
    path("battle/campaign/<str:campaign>", views.battle_campaign, name="battle_campaign"),
    path("battle/engage", views.battle_engage, name="battle_engage"),
    path("battle/attack", views.battle_attack, name="battle_attack"),
    path("shop/state", views.shop_state, name="shop_state"),
    path("shop/open", views.shop_open, name="shop_open"),
    path("shop/consume", views.shop_consume, name="shop_consume"),
    path("loadout/state", views.loadout_state, name="loadout_state"),
    path("loadout/equip", views.loadout_equip, name="loadout_equip"),
    path("loadout/unequip", views.loadout_unequip, name="loadout_unequip"),
    path("pvp/state", views.pvp_state, name="pvp_state"),
    path("pvp/defend", views.pvp_defend, name="pvp_defend"),
    path("pvp/attack", views.pvp_attack, name="pvp_attack"),
    # Dashboard page (Step 19)
    path("", views.dashboard_page, name="dashboard"),
]
