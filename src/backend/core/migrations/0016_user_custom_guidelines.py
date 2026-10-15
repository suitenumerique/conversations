# Generated on 2026-10-14

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0015_user_allow_datagouv_connector"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="custom_guidelines",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "Personal guidelines the user wants the assistant to follow, "
                    "appended to the system prompt on every conversation."
                ),
                verbose_name="custom guidelines",
            ),
        ),
    ]
