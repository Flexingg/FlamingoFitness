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
    # API (Steps 16-18)
    path("dashboard/state", views.dashboard_state, name="dashboard_state"),
    path("nutrition/", views.nutrition_state, name="nutrition_state"),
    path("hydration/", views.hydration_state, name="hydration_state"),
    path("leaderboard/weekly", views.leaderboard_weekly, name="leaderboard_weekly"),
    path(
        "webhooks/home-assistant",
        views.home_assistant_webhook,
        name="home_assistant_webhook",
    ),
    # Dashboard page (Step 19)
    path("", views.dashboard_page, name="dashboard"),
]
