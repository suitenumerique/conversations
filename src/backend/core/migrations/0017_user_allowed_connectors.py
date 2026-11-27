"""Replace the data.gouv opt-in boolean with a list of allowed connector slugs."""

from django.db import migrations, models


def forwards(apps, schema_editor):
    """Carry each data.gouv opt-in over as the `datagouv` slug."""
    del schema_editor
    User = apps.get_model("core", "User")
    User.objects.filter(allow_datagouv_connector=True).update(allowed_connectors=["datagouv"])


def backwards(apps, schema_editor):
    """Restore the boolean from the slug; other connectors' opt-ins are lost."""
    del schema_editor
    User = apps.get_model("core", "User")
    User.objects.filter(allowed_connectors__contains=["datagouv"]).update(
        allow_datagouv_connector=True
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0016_normalize_stored_user_emails"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="allowed_connectors",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Slugs of the MCP connectors the user switched on. This records a "
                    "choice, not an entitlement: a connector also has to be declared, "
                    "and the user has to be in its cohort."
                ),
                verbose_name="allowed connectors",
            ),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name="user",
            name="allow_datagouv_connector",
        ),
    ]
