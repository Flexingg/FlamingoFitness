"""Avatar service: user-uploaded profile pictures (docs/13 UI tune-up).

The ``User.avatar`` field is a plain URL string to keep the DiceBear default
and uploaded files interchangeable. When a player uploads a picture we:

  1. validate the file (magic bytes + size, no Pillow required),
  2. persist it under MEDIA_ROOT via the configured default storage,
  3. set ``user.avatar`` to the media-relative URL (e.g. ``/media/avatars/…``).

No schema change is needed - the field still stores a URL, so the leagues,
challenges, social and leaderboard serializers all keep working untouched.

Entry points:

  * ``save_avatar(user, upload)`` - validate + persist, returns ``(ok, value)``.
  * ``reset_avatar(user)`` - restore the DiceBear default.
  * ``avatar_url(user)`` - the current avatar (default fallback if blank).
"""

import logging
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

# The default cartoon avatar served when a user hasn't uploaded a picture.
DEFAULT_AVATAR = "https://api.dicebear.com/7.x/avataaars/svg?seed=Flamingo"

# Hard cap so a polygon-bomb PNG can't fill the disk (docs/11 gotcha).
MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5 MB

# Magic bytes -> file extension (Pillow-free sniffing).
_MAGIC = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpg",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"RIFF": "webp",  # confirmed below by checking for "WEBPVP8"
}

_AVATAR_DIR = "avatars"


def _err(message, status=400):
    return {"message": message, "status": status}


def _sniff_format(data):
    """Detect the image format from leading magic bytes (Pillow-free)."""
    head = data[:12]
    for magic, ext in _MAGIC.items():
        if head.startswith(magic):
            # WebP: eighth byte onward must read "WEBPVP8".
            if ext == "webp" and not head[8:12].startswith(b"WEBP"):
                continue
            return ext
    return None


def _validate(upload):
    """Return ``(error_or_None, (data, ext))``. Reads the whole (bounded) file."""
    data = upload.read(MAX_AVATAR_BYTES + 1)
    if len(data) > MAX_AVATAR_BYTES:
        return _err("Image is too large (max 5 MB)."), None

    if not data:
        return _err("No image data received."), None

    sniffed = _sniff_format(data)
    if sniffed is None:
        return _err("Unsupported image type. Please upload PNG, JPG, GIF or WebP."), None
    return None, (data, sniffed)


def save_avatar(user, upload):
    """Validate + persist an uploaded avatar and point ``user.avatar`` at it.

    Returns ``(True, media_url)`` on success or ``(False, error_dict)``.
    """
    error, parsed = _validate(upload)
    if error is not None:
        return False, error
    data, ext = parsed

    name = f"{_AVATAR_DIR}/{user.pk}_{uuid.uuid4().hex[:10]}.{ext}"
    try:
        default_storage.save(name, ContentFile(data))
    except OSError:
        logger.exception("Failed to store avatar for user %s", user.pk)
        return False, _err("Could not save your picture. Please try again.", 500)

    user.avatar = default_storage.url(name)
    user.save(update_fields=["avatar"])
    return True, user.avatar


def reset_avatar(user):
    """Revert to the default DiceBear avatar."""
    user.avatar = DEFAULT_AVATAR
    user.save(update_fields=["avatar"])
    return True, user.avatar


def avatar_url(user):
    """The user's current avatar, falling back to the DiceBear default."""
    return (user.avatar or "").strip() or DEFAULT_AVATAR
