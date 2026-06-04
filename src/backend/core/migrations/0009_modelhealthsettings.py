from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0008_maintenancemode"),
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
            ],
            options={
                "verbose_name": "Model Health Settings",
            },
        ),
    ]
