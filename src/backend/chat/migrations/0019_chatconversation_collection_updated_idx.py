from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    # CONCURRENTLY cannot run inside a transaction, and the conversation table is
    # large enough in production that a plain CREATE INDEX would block writes.
    atomic = False

    dependencies = [
        ("chat", "0018_chatconversation_owner_noproj_updated_idx"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="chatconversation",
            index=models.Index(
                condition=models.Q(collection_id__isnull=False),
                fields=["updated_at"],
                name="chat_conv_collection_upd_idx",
            ),
        ),
    ]
