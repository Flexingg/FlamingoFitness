# Generated for FoodSnapDraft on 2026-09-02

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_waterbottle'),
    ]

    operations = [
        migrations.CreateModel(
            name='FoodSnapDraft',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.FileField(blank=True, null=True, upload_to='food_snaps/%Y/%m/')),
                ('image_base64', models.TextField(blank=True, default='', help_text='Base64 encoded photo for offline sync or direct client uploads.')),
                ('note', models.TextField(blank=True, default='', help_text="User-provided notes, e.g. 'Chipotle bowl with double chicken and brown rice'")),
                ('meal_type', models.CharField(default='Lunch', max_length=50)),
                ('entry_date', models.DateField(default=django.utils.timezone.localdate)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('analyzed', 'Analyzed / Ready for Review'), ('logged', 'Logged'), ('discarded', 'Discarded')], default='pending', max_length=20)),
                ('extracted_items', models.JSONField(blank=True, default=list, help_text='List of matched or estimated items: [{name, calories, protein, carbs, fat, quantity, unit, food_id, match_source, confidence}]')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='food_snap_drafts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
