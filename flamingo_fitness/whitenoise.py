"""WhiteNoise middleware subclass that also serves user-uploaded media.

Production runs Gunicorn behind a reverse proxy with no separate file server.
WhiteNoise handles collected /static/ assets; user-uploaded avatars live in
MEDIA_ROOT and must be served by the same process too. We subclass the shipped
middleware and register MEDIA_ROOT so ``GET /media/*`` resolves in production
(and the equivalent static() helper kicks in for local development).

See:
  * flamingo_fitness/settings.py - MEDIA_ROOT / MEDIA_URL
  * core/services/avatar.py     - the upload pipeline
"""

from django.conf import settings as django_settings

from whitenoise.middleware import WhiteNoiseMiddleware


class MediaServingWhiteNoise(WhiteNoiseMiddleware):
    """WhiteNoise middleware with MEDIA_ROOT registered in addition to /static/."""

    def __init__(self, get_response=None, **kwargs):
        super().__init__(get_response=get_response, **kwargs)
        media_root = getattr(self, "settings", django_settings).MEDIA_ROOT
        media_url = getattr(self, "settings", django_settings).MEDIA_URL or ""
        if media_root:
            self.add_files(root=media_root, prefix=media_url)
