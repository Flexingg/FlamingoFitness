"""ASGI config for the Flamingo Fitness project."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "flamingo_fitness.settings")

application = get_asgi_application()
