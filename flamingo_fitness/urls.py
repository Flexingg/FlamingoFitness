"""Root URL configuration for Flamingo Fitness."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("core.urls")),
    # Root path serves the dashboard template (Step 19).
    path("", include("core.urls")),
]

# In development Django serves uploaded media directly. Production relies on
# the WhiteNoise subclass (flamingo_fitness/whitenoise.py) for both /static/
# and /media/ under gunicorn, so this is only wired for DEBUG.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
