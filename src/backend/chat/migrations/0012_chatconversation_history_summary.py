from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0011_chatconversation_model_hrid"),
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
