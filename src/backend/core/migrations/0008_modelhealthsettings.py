from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_siteconfiguration_status_banner_content_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModelHealthSettings",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "poll_interval_minutes",
                    models.PositiveIntegerField(
                        default=5, help_text="Minimum minutes between two effective polling runs."
                    ),
                ),
                (
                    "last_run_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Timestamp of the last successful polling run.",
                        null=True,
                    ),
                ),
            ],
            options={
                "verbose_name": "Model Health Settings",
            },
        ),
    ]
