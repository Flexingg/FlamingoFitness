"""Root URL configuration for Flamingo Fitness."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("core.urls")),
    # Root path serves the dashboard template (Step 19).
    path("", include("core.urls")),
]
