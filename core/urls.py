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
    # Base-building meta-game (Step 25)
    path("base/", views.base_state, name="base_state"),
    path("base/start", views.base_start, name="base_start"),
    path("base/speedup", views.base_speedup, name="base_speedup"),
    path("base/collect", views.base_collect, name="base_collect"),
    path("base/customize", views.base_customize, name="base_customize"),
    path("base/staff", views.base_staff, name="base_staff"),
    path("base/evolve", views.base_evolve, name="base_evolve"),
    path("base/milestone", views.base_milestone, name="base_milestone"),
    # Dashboard page (Step 19)
    path("", views.dashboard_page, name="dashboard"),
]
