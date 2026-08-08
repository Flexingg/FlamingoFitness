import os
os.environ["POSTGRES_DB"] = ""
os.environ["DEMO"] = "True"
os.environ["DJANGO_SETTINGS_MODULE"] = "flamingo_fitness.settings"
import django

django.setup()

from django.test import override_settings
from django.contrib.auth import get_user_model
from core.models import UserIntegration, Provider, RawActivityLog

U = get_user_model()
u, _ = U.objects.get_or_create(username="eagerprobe")
UserIntegration.objects.update_or_create(
    user=u, provider=Provider.LIFTOSAUR, defaults={"credentials": {}, "is_active": True}
)

with override_settings(DEMO=True):
    from core.tasks import sync_liftosaur_for_user

    res = sync_liftosaur_for_user.apply(args=[u.id])
    print("successful:", res.successful())
    if not res.successful():
        print("TRACEBACK:\n", res.traceback)

print("liftosaur logs:", RawActivityLog.objects.filter(user=u, source=Provider.LIFTOSAUR).count())
