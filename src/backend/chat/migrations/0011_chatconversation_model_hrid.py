"""Persist the pinned LLM HRID on each conversation."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0010_alter_modelhealth_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatconversation",
            name="model_hrid",
            field=models.CharField(
                blank=True,
                help_text=(
                    "HRID of the LLM pinned to this conversation. Set on the first"
                    " message and kept for the whole conversation so a recovered main"
                    " model does not move ongoing chats."
                ),
                max_length=100,
                null=True,
            ),
        ),
    ]
