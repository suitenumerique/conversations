from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0007_chatconversationattachment_project_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatconversation",
            name="history_summary",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Latest generated conversation summary used as system context",
            ),
        ),
    ]
