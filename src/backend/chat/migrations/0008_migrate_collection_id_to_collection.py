"""Migrate legacy ChatConversation.collection_id to Collection model rows."""

from django.db import migrations


def forwards(apps, schema_editor):
    ChatConversation = apps.get_model("chat", "ChatConversation")
    Collection = apps.get_model("chat", "Collection")
    collections = [
        Collection(
            backend="albert",
            external_id=conversation.collection_id,
            name=f"conversation-{conversation.pk}",
            conversation=conversation,
        )
        for conversation in ChatConversation.objects.filter(
            collection_id__isnull=False,
        ).exclude(collection_id="")
    ]
    Collection.objects.bulk_create(collections)


def backwards(apps, schema_editor):
    Collection = apps.get_model("chat", "Collection")
    ChatConversation = apps.get_model("chat", "ChatConversation")

    for collection in Collection.objects.filter(conversation__isnull=False, backend="albert"):
        ChatConversation.objects.filter(pk=collection.conversation_id).update(
            collection_id=collection.external_id,
        )
    Collection.objects.filter(conversation__isnull=False, backend="albert").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0007_collection_collectiondocument_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
