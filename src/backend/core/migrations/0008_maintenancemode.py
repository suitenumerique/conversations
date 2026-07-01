from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_siteconfiguration_status_banner_content_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MaintenanceMode",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=False,
                        help_text="When checked, the app is in maintenance mode for end-users.",
                        verbose_name="Enabled",
                    ),
                ),
                (
                    "message",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Shown on the maintenance page. Leave blank for the default message.",
                        verbose_name="Message",
                    ),
                ),
                (
                    "starts_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="If set, maintenance is inactive before this date.",
                        null=True,
                        verbose_name="Starts at",
                    ),
                ),
                (
                    "ends_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="If set, maintenance is inactive after this date.",
                        null=True,
                        verbose_name="Ends at",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Maintenance Mode",
            },
        ),
    ]
