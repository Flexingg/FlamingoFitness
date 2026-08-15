"""Add User.theme preference (light / dark / device / time)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_challenge_leagueweek_flock_flockmembership_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="theme",
            field=models.CharField(
                choices=[
                    ("light", "Light"),
                    ("dark", "Dark"),
                    ("device", "Device"),
                    ("time", "Time"),
                ],
                default="device",
                help_text=(
                    "Appearance preference: force Light or Dark, follow the "
                    "device, or switch by time of day (dark 6pm-6am)."
                ),
                max_length=10,
            ),
        ),
    ]
