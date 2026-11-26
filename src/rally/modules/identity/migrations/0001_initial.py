import django.db.models.deletion  # noqa: F401
from django.db import migrations, models

import rally.core.clock


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Account",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("phone", models.CharField(blank=True, default="", max_length=32)),
                ("is_verified", models.BooleanField(default=False)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(default=rally.core.clock.now, editable=False)),
            ],
            options={
                "verbose_name": "account",
                "db_table": "account",
            },
        ),
    ]
