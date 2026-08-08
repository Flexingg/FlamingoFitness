"""WSGI config for the Flamingo Fitness project."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "flamingo_fitness.settings")

application = get_wsgi_application()
