"""WhiteNoise middleware subclass that also serves user-uploaded media.

Production runs Gunicorn behind a reverse proxy with no separate file server.
WhiteNoise handles collected /static/ assets; user-uploaded avatars live in
MEDIA_ROOT and must be served by the same process too. We subclass the shipped
middleware and register MEDIA_ROOT so ``GET /media/*`` resolves in production
(and the equivalent static() helper kicks in for local development).

Why a per-request resolver for /media/: WhiteNoise builds an in-memory index
of the files it can serve at startup and (in production) never refreshes it.
Avatars are uploaded *after* the process boots, so they are missing from that
snapshot and would 404 - which the frontend's onerror handler then hides by
falling back to the default DiceBear avatar (it looks like the upload never
saved). We keep the fast startup index for /static/ but resolve /media/*
straight from the filesystem on every request so freshly uploaded pictures
appear immediately.

See:
  * flamingo_fitness/settings.py - MEDIA_ROOT / MEDIA_URL
  * core/services/avatar.py      - the upload pipeline
"""

import os
from urllib.parse import urlparse

from django.conf import settings as django_settings

from whitenoise.middleware import WhiteNoiseMiddleware
from whitenoise.string_utils import ensure_leading_trailing_slash


def _media_url_prefix():
    """The normalised URL prefix (e.g. ``/media/``) for uploaded files."""
    raw = getattr(django_settings, "MEDIA_URL", "/media/")
    return ensure_leading_trailing_slash(urlparse(raw).path)


class MediaServingWhiteNoise(WhiteNoiseMiddleware):
    """WhiteNoise middleware serving /static/ plus freshly-uploaded /media/."""

    def __init__(self, get_response=None, **kwargs):
        try:
            super().__init__(get_response=get_response, **kwargs)
        except (FileNotFoundError, OSError):
            self.get_response = get_response
            self.static_root = getattr(django_settings, "STATIC_ROOT", None)
            self.static_prefix = getattr(django_settings, "STATIC_URL", "/static/")
            self.files = {}
            self.directories = []
        self.media_prefix = _media_url_prefix()
        media_root = getattr(django_settings, "MEDIA_ROOT", None)
        if not media_root:
            return

        # Startup snapshot: lets already-existing media use the fast dict path.
        if os.path.exists(media_root):
            try:
                self.add_files(root=media_root, prefix=self.media_prefix)
            except (FileNotFoundError, OSError):
                pass

        # Register the real directory so find_file() can stat MEDIA_ROOT at
        # request time. WhiteNoise's self.files is a startup-time snapshot and
        # won't contain pictures uploaded later - the exact /media/ case - so
        # we bypass that index for media and hit the filesystem instead.
        self.directories.append(
            (
                os.path.abspath(os.fspath(media_root)).rstrip(os.sep) + os.sep,
                self.media_prefix,
            )
        )

    def __call__(self, request):
        path = request.path_info
        if path.startswith(self.media_prefix):
            # Media changes at runtime, so always look on disk (never rely on
            # WhiteNoise's startup index). Unmatched media pass through so a
            # real 404 is still returned for genuinely missing files.
            static_file = self.find_file(path)
            if static_file is None:
                return self.get_response(request)
            return self.serve(static_file, request)
        return super().__call__(request)

