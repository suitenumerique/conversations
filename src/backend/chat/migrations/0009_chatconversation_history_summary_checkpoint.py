from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0008_chatconversation_history_summary"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatconversation",
            name="history_summary_checkpoint",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Number of pydantic history messages already compacted into history_summary",
            ),
        ),
    ]
