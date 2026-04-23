from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0006_chatproject_chatconversation_project"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE chat_chatconversation "
                        "ADD COLUMN IF NOT EXISTS history_summary text NOT NULL DEFAULT '';"
                    ),
                    reverse_sql=(
                        "ALTER TABLE chat_chatconversation "
                        "DROP COLUMN IF EXISTS history_summary;"
                    ),
                )
            ],
            state_operations=[
                migrations.AddField(
                    model_name="chatconversation",
                    name="history_summary",
                    field=models.TextField(
                        blank=True,
                        default="",
                        help_text=(
                            "Rolling summary of the conversation history used to compress context."
                        ),
                    ),
                )
            ],
        )
    ]
